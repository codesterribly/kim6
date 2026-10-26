# KIM6 — quick image and video actions for Dolphin

KIM6 adds practical image and video operations to KDE Dolphin’s context menus. Select files, choose an action, and process them without opening a full photo editor or video editor. The unified `kim_all` dispatcher runs the work and presents progress, prompts, and results.

KIM6 is designed for **KDE Plasma 6, KIO 6, and Dolphin**. It is a quick-workflow tool, not a replacement for digiKam, darktable, RawTherapee, GIMP, Lightroom, or Kdenlive.

## What you can do

- **Prepare images:** compress JPEGs, choose baseline or progressive JPEG, resize to a bound or percentage, and convert formats.
- **Transform photographs:** rotate by common or custom angles, use EXIF auto-orientation, flip, or flop.
- **Export and share:** create web-ready images with color management, prepare email attachments, or make a simple MP4 slideshow.
- **Manage metadata and names:** strip all or selected GPS/AI metadata, edit creator and rights, shift camera timestamps, synchronize EXIF and file dates, or rename by rules and EXIF date.
- **Create collections:** build HTML galleries, collages, PDF albums, print-layout PDFs, multi-page TIFFs, and animated GIFs.
- **Work with video:** transcode with H.264, H.265, or optional AV1 presets; extract frames or audio; remove audio without re-encoding video; or export a video segment to GIF.

There are five Dolphin service menus with 107 menu actions. The complete mapping, including menu IDs and exact dispatcher arguments, is in [the action inventory](docs/ACTIONS.md). For details, see the [feature guide](docs/FEATURES.md), [CLI reference](docs/CLI.md), [format guide](docs/FORMATS.md), [configuration reference](docs/CONFIGURATION.md), and [safety guide](docs/SAFETY.md). The [web manual](https://kim-6.github.io/kim6/) is intended for GitHub Pages.

## Install

Install runtime dependencies first; optional image delegates and video encoders depend on the formats you need. Then, from a Git checkout:

```sh
./install.sh
```

See [INSTALL.md](INSTALL.md) for dependencies, per-user and system installation, custom prefixes, upgrades, verification, and uninstall. The installed menus invoke the installed dispatcher by absolute path; `kim_all` does not need to be in `PATH`.

## Use

In Dolphin, select one or more local image or video files, right-click, and choose an operation from a KIM6 submenu. The menus pass selected files as separate arguments, so spaces and Unicode names are supported. Many actions also support direct invocation; begin with:

```sh
./src/bin/kim_all --help
```

For a safe smoke test, create a disposable copy of an image and run a create-mode action on that copy. See the [CLI reference](docs/CLI.md) for examples and output policies.

## Safe output behavior

Generated output is staged and validated before publication. Create mode does not replace occupied paths. An action that supports overwrite only replaces the explicitly authorized target after successful validation. Web export, email preparation, video utilities, and slideshows always create derivatives and never replace selected sources. Metadata, timestamps, and permissions follow action-specific policies; they are not all treated alike.

## Project status and testing

Processing features are frozen for the first polished release. The unified dispatcher and menus are covered by a 924-test canonical suite; one test is skipped when the optional JPEG XL encoder is unavailable. Run it with:

```sh
python3 -B tests/run.py
```

The development machine’s KDE Frameworks/KIO 6.29 has an upstream submenu regression, so live Dolphin submenu acceptance is deferred. KIM6 keeps its submenu declarations; automated menu and isolated installation tests are used until the KDE issue is fixed or another supported desktop is available.

## History, contributors, and license

KIM descends from work begun for KDE 3 and carried through community KDE 4/5 forks. KIM6 is the Plasma 6 continuation. The dispatcher retains attribution to Charles Bouveyron, Tomáš Hnyk, Raphaël Pinson, Mathieu Vilaplana, and KIM6 contributors; individual historical scripts retain their original notices. See [ABOUT](ABOUT), [ChangeLog](ChangeLog), and the [historical documentation archive](docs/archive/upstream/ARCHIVE.md).

KIM6 is distributed under the GNU General Public License, version 3 or later. Read [LICENSE.md](LICENSE.md).
