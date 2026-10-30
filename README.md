# KIM6

**Image and Video Tools for KDE Dolphin**

KIM6 adds image and video tools directly to KDE Dolphin's right-click menus. Resize photographs, convert file formats, compress images, remove metadata, create galleries, and process videos without opening a separate editing application.

Select one file or an entire group of files, right-click, and choose what you want to do.

KIM6 is a modernized rewrite of the KDE Image Menu project, bringing its familiar tools to KDE Plasma 6 while adding new capabilities and improving how files are handled.

## Quick Start

Select one or more photographs in Dolphin, right-click, and choose a KIM6 action. Create mode saves separate outputs and preserves selected originals where supported. `KIM_POLICY=create` selects Create mode automatically; `KIM_POLICY=prompt` displays the output-policy dialog.

| Task | Dolphin menu action | Example output |
|---|---|---|
| Resize a photograph | KIM6 — Compress, resize and web export → Resize (1600x1600 pixels) | `lake_resized.jpg` |
| Compress a JPEG | KIM6 — JPEG compression → JPEG quality: 70% | `lake_compressed.jpg` |
| Convert PNG to JPEG | KIM6 — Convert and transform → Convert to JPEG | `garden.jpg` |
| Remove GPS coordinates | KIM6 — Publish and organize → Remove GPS coordinates… | `trip_gps.jpg` |
| Resize several photographs | KIM6 — Compress, resize and web export → Resize (800x800 pixels) | `lake_resized.jpg`, `garden_resized.jpg`, `portrait_resized.jpg` |

These examples assume default suffix naming. KIM6 numbers output names when collisions occur. Resize presets preserve aspect ratio and can enlarge smaller images. JPEG compression is lossy, and JPEG does not support PNG transparency.

GPS removal targets recognized coordinate fields but does not guarantee complete location anonymization. If no matching fields are present, no new copy is created. Completed batch outputs remain available even if a later item fails.

See [Command and Configuration Reference](docs/commandconfig.md#configuration-and-defaults) for filename and output-policy settings.

## Features

### Resize, compress, and convert images

- **Resize images:** Choose maximum-width/height presets, enter custom dimensions, or use percentage resizing (1–1000%; above 100% enlarges). Presets preserve the aspect ratio and may enlarge smaller inputs. Process multiple photographs together.
- **Compress JPEGs:** Select a JPEG quality level, progressive or baseline encoding, and optional Huffman-table optimization. Smaller files are not guaranteed at every setting.
- **Prepare images for the web:** Resize and optimize photographs, with options for output quality and color profiles.
- **Convert formats:** Convert between JPEG, PNG, GIF, BMP, TIFF, WebP, and additional formats such as AVIF, HEIC/HEIF, JPEG XL, and JPEG 2000 (including lossless/lossy JP2 modes) when supported by your system. Frame and color-profile checks reject known unsafe or unsupported results.
- **Rotate and flip:** Rotate images manually or use their EXIF orientation information.

### Organize photographs and manage metadata

- **Manage privacy and metadata:** Remove recognized GPS coordinates, AI-generation fields, or all supported metadata. GPS-only cleanup is not complete location anonymization; C2PA/Content Credentials removal cannot be guaranteed.
- **Manage photo dates:** Rename photographs using EXIF dates, shift camera wall-clock timestamps, and synchronize EXIF and filesystem dates in either direction. Time shifts are not automatic timezone conversions; subsecond and offset behavior depends on the action.
- **Update copyright information:** Add or modify copyright metadata across multiple photographs.
- **Control what gets preserved:** Choose appropriate metadata and output behavior for different operations.

### Create and share

- **Email photographs:** Send original images or create smaller copies suitable for email attachments.
- **Build photo galleries:** Generate browsable HTML galleries, including the Dark Portfolio presentation.
- **Create collages:** Arrange multiple images using grid, mosaic, hero, filmstrip, or scattered-photo layouts. Adjust canvas, background, spacing, frames, and shadows where supported.
- **Create PDF albums and print layouts:** Prepare photographs for viewing or printing, including printable contact-sheet layouts.
- **Work with TIFF and GIF:** Combine images into multipage TIFF files or animated GIFs.

### Video tools

KIM6 also includes video operations directly in Dolphin:

- Resize and convert videos using H.264, H.265 (HEVC), and AV1 encoding.
- Choose from predefined output resolutions and quality settings.
- Extract individual frames or create contact sheets.
- Save audio from video files.
- Remove audio tracks from videos to create silent copies.
- Convert short video clips into animated GIFs.
- Create MP4 slideshows from photographs.

Available video codecs depend on FFmpeg and the encoders installed on your system.

## How KIM6 works

KIM6 appears in Dolphin's context menu when you right-click supported image or video files. Select several files to apply supported operations to a group.

Most resizing, compression, and conversion actions offer **Create new files (originals untouched)** or **Overwrite originals (confirmation required)**. Replacing originals requires a second explicit confirmation that identifies the affected files and operation. `KIM_POLICY=create` selects separate outputs where supported; `KIM_POLICY=prompt` displays the output-policy dialog.

Rotation, EXIF auto-orientation, flip, and flop support both Create and Overwrite modes. Create mode saves transformed copies while preserving the selected originals. Overwrite mode replaces the originals only after explicit review and confirmation. Metadata editing and renaming have their own create/overwrite handling, including warnings when original filenames will be removed. Web export, email preparation, video frame/audio/GIF utilities, and slideshows create derivatives. **Video transcoding** can instead replace an original after explicit overwrite confirmation. Completed batch results remain available if a later item fails, while staged invalid results are not published.

Create mode numbers occupied output filenames and respects configurable prefix/suffix affix placement (for example, `web_photo.jpg` versus `photo_web.jpg`). Output publication rejects unsafe source aliases and linked destinations where relevant. **Animated APNG is deliberately refused by Resize, Web Export and resized email preparation** rather than being flattened to a still image; dedicated APNG conversion remains available when the required tools support it.

See [Getting Started](#quick-start) for examples, [Safe Handling](docs/commandconfig.md#output-and-file-handling) for details, and [Supported Formats](docs/FORMATS.md) for decoder and encoder limits.

## Installation

KIM6 is designed for KDE Plasma 6 and Dolphin.

Dolphin includes a **Download New Services** feature under its configuration settings, which can install service-menu extensions from KDE's online catalog. You can also find the existing project on the [KDE Store](https://store.kde.org/p/2307290/).

**Important:** This version of KIM6 is a substantial rewrite. The version currently available through Dolphin or the KDE Store may still be an earlier release. To use the rewrite, download the corresponding source version and install it manually.

From a checkout containing the rewrite:

```bash
./install.sh
```

Restart Dolphin after installing, then right-click a supported image or video to find the KIM6 menus.

To uninstall KIM6, run `./uninstall.sh` from the source directory. See [Installation Instructions](INSTALL.md) for dependencies, upgrades, system-wide installation, custom directories, and uninstall options.

## Documentation

- [Getting Started](#quick-start) — Common tasks and examples.
- [User Manual](docs/index.html) — Using KIM6's image and video tools.
- [Complete Action List](docs/ACTIONS.md) — Available Dolphin menu actions.
- [Supported Formats](docs/FORMATS.md) — Image and video format support.
- [Configuration](docs/commandconfig.md) — Customizing KIM6's behavior.
- [Development](docs/DEVELOPMENT.md) — Technical information and contributing.

You can also report bugs or suggest improvements through the project's [GitHub Issues](https://github.com/KIM-6/kim6/issues).

## Project history

KIM, the KDE Image Menu, began during the KDE 3 era in the mid-2000s. Its goal was simple: provide useful image-processing tools from the file manager without requiring users to open a separate application.

The project continued through KDE 4, KDE 5, and KDE 6, with contributions from multiple developers and maintainers.

- [Original KIM project](http://bouveyron.free.fr/kim/index.html)
- [KIM5 for KDE Plasma 5](https://github.com/caco3/kim5)
- [KIM6 project](https://github.com/KIM-6/kim6)

This rewrite preserves the original idea while consolidating the processing tools, adding modern image and video formats, and expanding metadata and batch-processing capabilities.

Credit belongs to the original developers, including Charles Bouveyron and Tomáš Hnyk, along with the contributors who maintained and adapted KIM for later KDE versions. See [ABOUT](ABOUT) for project credits.

## AI Attribution

KIM6's current code was rewritten by hand. Much of the unit testing and portions of the documentation were generated with the assistance of a self-trained, locally hosted AI model specializing in unit testing and technical documentation.

## License

KIM6 is free and open-source software licensed under the [GNU General Public License, version 3 or later](LICENSE.md).