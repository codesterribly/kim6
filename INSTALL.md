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

Run the same `./install.sh` command and prefix used for the existing installation. Repeating installation is supported. The installer updates the fixed runtime inventory and five menus one file at a time. Each individual replacement is written to a temporary sibling and renamed into place, so a single file is not left partly written.

The `.kim6-owned` marker identifies the runtime directory. The installer can adopt an empty `kim6` directory after an interrupted first install, but refuses populated markerless runtimes; the uninstaller requires the marker and will not infer ownership from a matching dispatcher. The five named menu files are identified by their KIM6 marker or a recognized previous KIM command. The installer refuses unrelated same-name menus, symlinked targets, and runtime trees containing symlinks. Known legacy commands are removed only when their bytes match the corresponding repository script; a modified legacy command stops the upgrade so you can move it aside yourself. Unknown files inside the runtime are retained.

**Upgrade safety is intentionally simpler than the earlier transactional installer.** There is no digest manifest, customization recovery copy, whole-install staging area, or automatic rollback. Customized contents at listed KIM runtime or marked menu paths are replaced or removed as part of upgrade/uninstall. If installation is interrupted, some files may be from the new version and others from the old version; rerun the same install command to finish. An error does not mean earlier file replacements were undone. A hard kill or power loss can also leave a hidden temporary sibling; reruns do not delete unknown temporary paths. Save any edits to KIM-owned files before upgrading. Files outside the explicit inventory are not selected for deletion.

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

The installer checks the rendered menus for the installed dispatcher path, then refreshes the KDE cache best-effort after file updates when `kbuildsycoca6` is available. It no longer performs an isolated `kbuildsycoca6` validation before changing files. Restart Dolphin or rebuild its service-menu cache if entries do not appear. The development desktop uses KDE Frameworks/KIO 6.29, which has a known upstream `X-KDE-Submenu` regression. KIM6 retains its submenus; wait for the KDE fix or test on another supported Plasma 6 system rather than removing submenu declarations.

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

`uninstall.sh` also accepts `--no_message`. It removes only the five named menus when their KIM marker or a recognized previous KIM command establishes ownership, and only the listed runtime paths below a marked `kim6` directory. Known legacy commands are removed only when their contents match the repository copy; edited copies remain. Unrelated files remain, and the marker remains if unknown runtime data is still present so uninstall can be rerun. User edits to listed KIM-owned files are removed with those files. An unsafe runtime symlink or symlinked menu target stops uninstall before removal. Empty known directories are removed when possible. Uninstallation is not transactional; if interrupted, rerun it after resolving the reported problem.

## Troubleshooting

- **Installer says `intltool-merge` is missing:** install the distribution package providing `intltool` and rerun the same command.
- **A format action is unavailable:** check the local ImageMagick coder list and relevant FFmpeg encoder; see [FORMATS.md](docs/FORMATS.md). Optional support varies by build.
- **Progress or cancellation does not work:** verify KDialog and `qdbus` are installed and that Dolphin runs in a KDE graphical D-Bus session.
- **The menu is missing:** confirm the files are under the active user/system `kio/servicemenus` directory, restart Dolphin, and check the KDE cache. Keep the submenu declaration; the 6.29 regression is external to KIM6.
- **Installation failed or was interrupted:** some listed files may already have been updated. Rerun the same install command after fixing the reported problem; it is designed to complete an incomplete installation. Review and save any local edits to listed KIM-owned files before doing so.

For reproducible reports, include the KIM6 commit, Plasma/KIO version, action and exact arguments, relevant dependency versions/coder output, and whether the issue reproduces on disposable test files.

More detail: [configuration](docs/CONFIGURATION.md), [safety behavior](docs/SAFETY.md), and [feature inventory](docs/ACTIONS.md).
