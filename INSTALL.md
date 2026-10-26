# Install KIM6

KIM6 adds five service menus to KDE Dolphin and installs the `kim_all` program and resources those menus use. It is designed for KDE Plasma 6 and Dolphin's KIO service-menu system. It does not target the older KDE 4 or KDE 5 menu systems.

## Before you install

You need a KDE Plasma 6 desktop with Dolphin and Git to get the project checkout shown below. The installer also needs `intltool-merge` to prepare the translated menus. During normal use, KIM6 checks for the tools an action needs. Image work uses ImageMagick 7; metadata and photo-date work uses ExifTool; video work uses FFmpeg and `ffprobe`. KDialog and `qdbus` provide the Dolphin dialogs and progress display. Optional ImageMagick format support, ICC profiles, and video encoders vary by distribution. See [Formats and codecs](docs/FORMATS.md) for details.

## Install for your user

Get the project and run the installer:

```sh
git clone https://github.com/KIM-6/kim6.git
cd kim6
./install.sh
```

This installs for your current user under `${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus`. You do not need administrator access for this installation.

When installation finishes, restart Dolphin or close and reopen it. Select a local image or video, right-click, and look for the KIM6 menus. Depending on the action, you will see menus for JPEG compression, resizing and sharing, conversion and transforms, video, and publishing or organizing.

## Check that it worked

The service-menu directory should contain these five files and a `kim6` folder:

```text
kim_compress.desktop
kim_compressandresize.desktop
kim_convertandrotate.desktop
kim_compressandresizevideo.desktop
kim_publication.desktop
kim6/bin/kim_all
```

The `kim_all` program should be executable. The `.desktop` files are data files, normally installed with permissions `0644`; do not make them executable. The menus call `kim_all` by its installed path, so it does not need to be in your shell's `PATH`.

You can check the installed program from a terminal without opening Dolphin. Replace the example path if you used a custom location:

```sh
"${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus/kim6/bin/kim_all" --help
```

If the files are present but a KIM6 submenu does not appear, restart Dolphin and check the service-menu location and KDE cache. On KDE Frameworks/KIO 6.29, an upstream submenu display problem is known to affect this style of menu. KIM6 keeps its submenus; do not remove `X-KDE-Submenu` to work around it. A future KDE fix or testing on another supported Plasma 6 system is the right check.

## Upgrade or reinstall

To update KIM6, use the newer checkout and run the same install command with the same prefix. For a normal user install:

```sh
cd ~/path/to/kim6
git pull
./install.sh
```

Repeated installation is supported. KIM6 updates its listed program files and the five named menus individually. If an upgrade is interrupted, some files may already be updated; fix the reported problem and run the same command again to finish.

The installer uses a `.kim6-owned` marker for the runtime folder and a KIM marker or recognized older KIM command to identify named service menus. It refuses populated runtime folders without the marker, unrelated same-name menu files, and symlinked installation paths. It removes known old KIM commands only when they match the repository copy. Unknown files are left in place. User edits inside listed KIM6 files are replaced during upgrade, so save those edits first.

Each file is prepared beside its destination and renamed into place. The whole installation is not one transaction and does not roll back files already replaced. If installation stops partway through, rerunning it completes the update. A hard interruption may leave a hidden temporary file; the installer does not guess whether an unknown leftover belongs to KIM6.

## Uninstall

Use the checkout that contains `uninstall.sh` and the same prefix used to install KIM6. For the default user location:

```sh
./uninstall.sh
```

For a custom prefix, pass the service-menu directory itself:

```sh
./uninstall.sh --prefix "$HOME/.local/share/kio/servicemenus"
```

For a system install, use the same system prefix and administrator rights:

```sh
sudo ./uninstall.sh --prefix /usr/local/share/kio/servicemenus
```

The uninstaller removes the five recognized KIM menus and the explicit KIM runtime inventory only when the runtime has its `.kim6-owned` marker. It will not infer runtime ownership from a matching program file alone. Unknown files remain, and the marker stays if unknown runtime data prevents removal of the folder. Uninstall is not transactional; if interrupted, rerun it after resolving the reported problem. It does not remove unrelated files by name pattern.

After a successful uninstall, the recognized KIM menu entries and listed KIM6 program resources are removed. If unknown files remain in the runtime folder, that folder and its marker remain too. Restart Dolphin to refresh the menus.

## Advanced installation locations

The `--prefix` option names the `servicemenus` directory, not the `kio` parent and not the KIM runtime directory. To choose a user location explicitly:

```sh
./install.sh --prefix "$HOME/.local/share/kio/servicemenus"
```

To install for all users in the common local share location:

```sh
sudo ./install.sh --prefix /usr/local/share/kio/servicemenus
```

When run as root without `--prefix`, the installer uses the first entry in `${XDG_DATA_DIRS:-/usr/local/share:/usr/share}` and appends `/kio/servicemenus`. Prefer an explicit prefix when installing system-wide so it is clear which location will be changed. The installer creates a missing destination directory.

The installer changes files only in that service-menu directory and its `kim6` subdirectory, and may refresh the KDE service cache when `kbuildsycoca6` is available. It does not install system packages, change KDE settings, or modify your photographs and videos.
