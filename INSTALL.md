# Install KIM6

KIM6 adds five image and video menus to KDE Dolphin. This version is a substantial rewrite of the original project and runs on KDE Plasma 6.

## Install through Dolphin

Dolphin can install service menus from its online catalog. Open **Settings → Configure Dolphin → Services**, then choose **Download New Services** and search for KIM6. Install the version shown there.

The rewritten KIM6 may not yet be available through that catalog. The KDE Store may still offer an earlier version; check the release information before installing if you specifically want this rewrite.

## Install this rewrite manually

You need a KDE Plasma 6 system with Dolphin. To install from the project checkout, you also need Git and `intltool-merge`. The installer uses `msgfmt` when available to compile translations; if it is missing, the menus still install without compiled message catalogs. For photo actions, install ImageMagick 7. ExifTool is needed for metadata and photo-date actions; FFmpeg and `ffprobe` are used for video. KDialog and `qdbus` provide dialogs and progress. Email actions also need a supported mail application. Optional image formats and video codecs depend on your system; see [Formats and codecs](docs/FORMATS.md).

Download the current source checkout and install it for your user:

```sh
git clone https://github.com/KIM-6/kim6.git
cd kim6
./install.sh
```

If you downloaded a source release archive instead, extract it and run `./install.sh` from the extracted project folder.

The installer adds the KIM6 menus and program files to your user service-menu folder. Restart Dolphin, select an image or video, and right-click. You should see five KIM6 submenus. The `kim_all` program is installed with those menus and does not need to be in your shell's `PATH`.

To check the installed dispatcher without opening Dolphin:

```sh
"${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus/kim6/bin/kim_all" --help
```

If the files are installed but the menus do not appear, restart Dolphin and check the path above. KDE Frameworks/KIO 6.29 has a known upstream issue affecting submenu display. KIM6 keeps its submenus; do not remove them as a workaround.

## Upgrade or reinstall

Use the newer checkout and run `./install.sh` again. Installation is performed one file at a time. If it is interrupted, run the installer again to finish. Known KIM6 files are replaced, while unrelated files in the installation folder are left alone. If you changed a KIM6 menu or program file yourself, save a copy before upgrading because the installer replaces it.

## Uninstall

From the same checkout, run:

```sh
./uninstall.sh
```

The uninstaller removes the five recognized KIM6 menus and the known KIM6 program files. It leaves unrelated files in place. Restart Dolphin after removal.

## Advanced installation locations

To choose a service-menu folder explicitly, pass that folder to `--prefix`:

```sh
./install.sh --prefix "$HOME/.local/share/kio/servicemenus"
```

For a system-wide install, use an explicit system folder and administrator rights:

```sh
sudo ./install.sh --prefix /usr/local/share/kio/servicemenus
```

Pass the same folder when uninstalling:

```sh
sudo ./uninstall.sh --prefix /usr/local/share/kio/servicemenus
```

The installer creates the chosen folder if needed. It does not install system packages, change KDE settings, or modify your photographs and videos.
