# KIM6

**Image and Video Tools for KDE Dolphin**

KIM6 adds image and video tools directly to KDE Dolphin's right-click menus. Resize photographs, convert file formats, compress images, remove metadata, create galleries, and process videos without opening a separate editing application.

Select one file or an entire group of files, right-click, and choose what you want to do.

KIM6 is a modernized rewrite of the KDE Image Menu project, bringing its familiar tools to KDE Plasma 6 while adding new capabilities and improving how files are handled.

## Quick Start

Select one or more photographs in Dolphin, right-click, and choose a KIM6 action. To configure how KIM6 handles your files, open **Actions → KIM6 — Settings/About → Settings**. You can choose whether supported operations create separate files automatically or ask you how to proceed. Save your preferences once, and KIM6 uses them for subsequent operations. Creating separate files preserves the selected originals.

| Task | Dolphin menu action | Example output |
|---|---|---|
| Resize a photograph | KIM6 — Resize/Rotate → Resize to 1600 × 1600 | `lake_resized.jpg` |
| Compress a JPEG | KIM6 — Convert/Compress → Compress Recommended | `lake_compressed.jpg` |
| Convert PNG to JPEG | KIM6 — Convert/Compress → Convert to JPEG | `garden.jpg` |
| Remove GPS coordinates | KIM6 — Organize/Metadata → Strip GPS Metadata | `trip_gps.jpg` |
| Remove recognized AI metadata | KIM6 — Organize/Metadata → Strip AI Metadata | `portrait_ai.jpg` |
| Resize several photographs | KIM6 — Resize/Rotate → Resize to 1280 × 1280 | `lake_resized.jpg`, `garden_resized.jpg`, `portrait_resized.jpg` |

These examples assume default suffix naming. KIM6 numbers output names when collisions occur. Resize presets preserve aspect ratio and can enlarge smaller images. JPEG compression is lossy, and JPEG does not support PNG transparency.

GPS removal targets recognized coordinate fields, but other metadata or visible scene details may still reveal a location. AI metadata removal targets recognized generation fields, but generator-specific metadata and signed C2PA / Content Credentials may remain. The examples assume Create mode and, for AI removal, a file containing recognized AI metadata. If no matching GPS fields are present, no GPS-stripped copy is created. Completed batch outputs remain available even if a later item fails.

Use **KIM6 — Settings/About → Settings** to change your defaults. For advanced configuration and command-line overrides, see [Command and Configuration Reference](docs/commandconfig.md#configuration-and-defaults).

## Features

### Resize, compress, and convert images

- **Resize images:** Choose maximum-width/height presets, enter custom dimensions, or use percentage resizing (1–1000%; above 100% enlarges). Presets preserve the aspect ratio and may enlarge smaller inputs. Process multiple photographs together.
- **Compress JPEGs:** Select a JPEG quality level, progressive or baseline encoding, and optional Huffman-table optimization. Smaller files are not guaranteed at every setting.
- **Prepare images for the web:** Export JPEG, PNG, WebP, or AVIF derivatives. JPEG, WebP and AVIF have separate quality defaults in Settings; PNG remains lossless. Color-profile handling can also be configured.
- **Convert formats:** Convert between JPEG, PNG, GIF, BMP, TIFF, WebP, and additional formats such as AVIF, HEIC/HEIF, JPEG XL, and JPEG 2000 (including lossless/lossy JP2 modes) when supported by your system. Frame and color-profile checks reject known unsafe or unsupported results.
- **Rotate and flip:** Rotate images manually or use their EXIF orientation information.

### Organize photographs and manage metadata

- **Manage privacy and metadata:** Use **Strip GPS Metadata** to remove recognized coordinates, **Strip AI Metadata** to remove recognized AI-generation fields, or **Strip Metadata** for broader metadata removal. GPS-only cleanup does not guarantee location anonymization. AI-only cleanup cannot guarantee removal of every generator-specific field or signed C2PA / Content Credentials.
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

KIM6 also includes video operations directly in Dolphin. H.264 and H.265 have six MP4 presets each; AV1 has six MP4 presets:

- Resize and convert videos using H.264, H.265 (HEVC), and AV1 encoding.
- Choose from predefined output resolutions and quality settings.
- Extract individual frames or create contact sheets.
- Save audio from video files.
- Remove audio tracks from videos to create silent copies.
- Convert short video clips into animated GIFs.
- Create MP4 slideshows from photographs.

Available video codecs depend on FFmpeg and the encoders installed on your system.

## How KIM6 works

KIM6 adds image and video tools to Dolphin's right-click menu. Select a photo or video, right-click it, and choose what you want to do. You can also select multiple files to process them together.

**Keeping your originals safe**

KIM6 can create new files while leaving your originals untouched, or ask how you want to proceed when an action supports replacing them. You can choose the default behavior under **Actions → KIM6 — Settings/About → Settings**. Replacing original files requires an additional confirmation, so KIM6 won't silently overwrite them.

Resizing, compression, conversion, rotation, and flipping follow these settings where supported. Renaming and metadata editing have their own safeguards, including warnings before original filenames are removed. Other operations, such as web export, email preparation, slideshows, and extracting video frames or audio, create separate results. Video transcoding can also replace an original, but only with explicit confirmation.

**Filenames and batch processing**

When KIM6 creates a new file, it avoids overwriting an existing file by adding a number to the output filename when necessary. You can also choose whether descriptive labels appear before or after the filename, such as `web_photo.jpg` or `photo_web.jpg`.

When processing several files, KIM6 keeps the results that completed successfully, even if a later file fails. Failed or invalid results are not published as completed files.

For examples, see [Getting Started](#quick-start). More detailed information about file protection and settings is available under [Safe Handling](docs/commandconfig.md#output-and-file-handling), while [Supported Formats](docs/FORMATS.md) explains format compatibility, encoder requirements, and restrictions.

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
- [User Guide](docs/index.html) — Using KIM6's image and video tools.
- [Complete Action List](docs/ACTIONS.md) — Available Dolphin menu actions.
- [Supported Formats](docs/FORMATS.md) — Image and video format support.
- [Configuration](docs/commandconfig.md) — Customizing KIM6's behavior.
- [Development](docs/DEVELOPMENT.md) — Technical information and contributing.

For source and project updates, see [this KIM6 rewrite](https://github.com/codesterribly/kim6). Report bugs or suggest improvements through [GitHub Issues](https://github.com/codesterribly/kim6/issues). The original project remains credited in the history section below.

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