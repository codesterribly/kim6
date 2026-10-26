<p align="center">
  <img src="graphics/Logo_1280x640_white_background.png" alt="KIM6 project logo" width="320">
</p>

<h1 align="center">KIM6</h1>

<p align="center">Image and video tools in KDE Dolphin</p>

Right-click one or more files to resize, convert, compress, rotate, prepare photos for sharing, remove metadata, and handle other common tasks. KIM6 is for everyday jobs that do not need a full image or video editor.

## Common tasks

| Photos | Albums and video |
| --- | --- |
| Resize by dimensions or percentage, compress JPEGs, convert formats, rotate and flip images. | Make galleries, collages, PDF albums, TIFFs and GIFs. Encode videos, extract frames or audio, and create simple MP4 slideshows. |
| Prepare web and email copies, manage photo dates, and edit or remove metadata. | Process several selected files together where the action supports batches. |

Some actions can replace a selected file after you authorize it. Others always make a separate result. Choose **Create new** to keep the selected original when an action offers that choice. See [Safe handling](docs/SAFETY.md) for details.

## Dolphin screenshot

*An authentic screenshot using anonymous demonstration files will be added after capture on a KDE system with working submenus. The development system has a KDE submenu issue, so no interface mockup is shown here.*

## Install

KIM6 is designed for KDE Plasma 6 and Dolphin. This rewrite may not yet be available through Dolphin's **Download New Services** catalog; the KDE Store may still show an earlier version. To install this rewrite from a source checkout:

```sh
git clone https://github.com/KIM-6/kim6.git
cd kim6
./install.sh
```

Restart Dolphin, select an image or video, and right-click to find the KIM6 menus. See [Install KIM6](INSTALL.md) for requirements, upgrades, and uninstall instructions.

## Help and project history

Start with the [Getting Started guide](docs/GETTING_STARTED.md), the [HTML manual](https://kim-6.github.io/kim6/), or the [complete action list](docs/ACTIONS.md). Technical references cover [formats](docs/FORMATS.md), [configuration](docs/CONFIGURATION.md), and [safe handling](docs/SAFETY.md).

KIM began as a KDE image menu project and has been continued by contributors across later KDE releases. Historical credits are in [ABOUT](ABOUT) and the [archive index](docs/archive/upstream/ARCHIVE.md). KIM6 is licensed under the [GNU General Public License, version 3 or later](LICENSE.md).
