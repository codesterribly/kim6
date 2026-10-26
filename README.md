# KIM6: image and video tools for KDE Dolphin

KIM6 adds image and video tools to KDE Dolphin. Select a file, right-click, and choose an action to resize, convert, compress, rotate, prepare an image for sharing, remove metadata, and do other everyday jobs. You can select several files and process them together.

For these routine tasks, you do not need to open a full photo or video editor. KIM6 is designed for KDE Plasma 6 and Dolphin. It complements tools such as digiKam, darktable, GIMP, RawTherapee, and Kdenlive; it is not a photo catalog, RAW developer, or video editor.

## Common tasks

- Resize photographs by a maximum size or percentage, or make JPEG copies at a chosen quality.
- Convert common image formats, rotate or flip photos, and prepare web or email copies.
- Remove GPS or other selected metadata, edit creator and copyright details, and work with camera dates.
- Make galleries, collages, PDF albums, multi-page TIFFs, and GIF animations.
- Compress videos, extract frames or audio, remove video audio, and make simple slideshows.

KIM6 installs five Dolphin menus. The [complete menu inventory](docs/ACTIONS.md) lists every action. The [Getting Started guide](docs/GETTING_STARTED.md) walks through common jobs. More detailed information is in the [installation guide](INSTALL.md), [feature guide](docs/FEATURES.md), [format guide](docs/FORMATS.md), [configuration reference](docs/CONFIGURATION.md), and [safety guide](docs/SAFETY.md). The [HTML manual](https://kim-6.github.io/kim6/) is also available.

## Install and use

KIM6 is intended for KDE Plasma 6 and Dolphin. Install the tools needed for the formats and actions you plan to use, then install KIM6 from a checkout:

```sh
git clone https://github.com/KIM-6/kim6.git
cd kim6
./install.sh
```

Restart Dolphin if the menus do not appear. After installation, select one or more local files, right-click, and look for the KIM6 menus. See [INSTALL.md](INSTALL.md) for dependencies, system or custom locations, upgrades, and removal.

For a first try, select `photo.jpg` and choose **KIM6 — Compress, resize and web export → Resize (1600x1600 pixels)**. Choose **Create new** if asked; `photo_resized.jpg` appears beside the original.

## What happens to the originals?

Many image actions ask whether to create a new file or replace the selected file, unless you have already set an output preference. Choose **Create new** to keep the original. Actions with collision-numbered outputs choose another name if needed; other workflows may ask for a destination or report a conflict. Web export, resized email attachments, video frame/audio/GIF tools, and slideshows create derived files only. Full-size email mode attaches selected originals without changing them. Video transcoding, rotation, flipping, and some metadata and date actions can replace a selected file when you authorize it. Rename actions have their own move/copy choices.

Different operations preserve different things. JPEG conversion or compression can change image detail, and some formats cannot store transparency or animation. GPS-only removal leaves other metadata in place; full metadata removal removes much more. Read [Safe handling of originals](docs/SAFETY.md) before choosing replacement as a default.

## Help, history, and license

Use the Manual, License, and About entries in Dolphin for installed resources. For a problem, see the [safety and troubleshooting guide](docs/SAFETY.md) and include the action, KIM6 revision, and relevant tool versions in a report. Avoid sharing private photographs unless you have permission.

KIM descends from work begun for KDE 3 and continued through community KDE 4 and 5 versions. KIM6 carries that work forward for Plasma 6. Original contributors and historical notices are retained in [ABOUT](ABOUT), [ChangeLog](ChangeLog), and the [historical documentation archive](docs/archive/upstream/ARCHIVE.md).

KIM6 is free software under the GNU General Public License, version 3 or later. See [LICENSE.md](LICENSE.md).
