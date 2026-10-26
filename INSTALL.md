
# Install KIM6

KIM6 adds five image and video service menus to KDE Dolphin. This version is a substantial rewrite of the original project and is designed for KDE Plasma 6.

## Install through Dolphin

Dolphin can install service menus from its online catalog. Open **Settings → Configure Dolphin → Services**, then choose **Download New Services** and search for KIM6.

The rewritten KIM6 may not yet be available through that catalog. The KDE Store may still offer an earlier version; check the release information if you specifically want this rewrite.

## Install this rewrite manually

KIM6 requires KDE Plasma 6 and Dolphin.

To install from a source checkout, you need `intltool-merge` (and Git if you are cloning the source). The installer uses `msgfmt` to compile translations when available; without it, the menus can still be installed in English.

KIM6 uses several common tools to process images and videos:

- **ImageMagick 7:** Image resizing, compression, conversion, galleries, and other image operations.
- **ExifTool:** Metadata management, photo dates, and copyright information.
- **FFmpeg and ffprobe:** Video conversion, audio extraction, animations, and slideshows.
- **KDialog and qdbus:** Dialogs, progress reporting, and interaction with KDE.
- **Email application:** Required for KIM6's email features.

Some image formats and video codecs require additional system support. See [Formats and codecs](docs/FORMATS.md).

Download or clone the KIM6 source code, then open a terminal in the project directory and run:

```sh
./install.sh
```

If you downloaded a source archive, extract it first and run the installer from the extracted folder.

The installer adds KIM6's program files and five service-menu definitions to your user installation directory. Restart Dolphin, then right-click an image or video to see the KIM6 actions available for that file type.

The `kim_all` program is installed with the menus and does not need to be added to your shell's `PATH`.

To check the installed program without opening Dolphin:

```sh
"${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus/kim6/bin/kim_all" --help
```

If the menus do not appear, restart Dolphin and verify that KIM6 was installed in a service-menu directory recognized by KDE.

**KDE Frameworks 6.29 issue:** Frameworks 6.29 introduced a regression that prevented some Dolphin service submenus from appearing. This was fixed in Frameworks 6.30. If you are using the affected version, update KDE Frameworks when a fixed package is available for your distribution.

KIM6 retains its normal submenu structure; you do not need to modify the service-menu files to work around this issue.

## Upgrade or reinstall

Use the newer source checkout and run `./install.sh` again. Installation is performed one file at a time. If it is interrupted, run the installer again to finish.

Known KIM6 files are replaced, while unrelated files in the installation folder are left alone. If you modified a KIM6 menu or program file yourself, save a copy before upgrading because the installer replaces it.

## Uninstall

From the source directory, run:

```sh
./uninstall.sh
```

The uninstaller removes the five recognized KIM6 menus and the known KIM6 program files. It leaves unrelated files in place. Restart Dolphin after removal.

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
