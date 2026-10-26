# KIM6

**Image and Video Tools for KDE Dolphin**

KIM6 adds image and video tools directly to KDE Dolphin's right-click menus. Resize photographs, convert file formats, compress images, remove metadata, create galleries, and process videos without opening a separate editing application.

Select one file or an entire group of files, right-click, and choose what you want to do.

KIM6 is a modernized rewrite of the KDE Image Menu project, bringing its familiar tools to KDE Plasma 6 while adding new capabilities and improving how files are handled.

## Features

### Resize, compress, and convert images

- **Resize images:** Choose common resolutions, enter custom dimensions, or resize by percentage. Process multiple photographs together.
- **Compress JPEGs:** Select a JPEG quality level to reduce file sizes for sharing or storage.
- **Prepare images for the web:** Resize and optimize photographs, with options for output quality and color profiles.
- **Convert formats:** Convert between JPEG, PNG, GIF, BMP, TIFF, WebP, and additional formats such as AVIF, HEIC/HEIF, JPEG XL, and JPEG 2000 when supported by your system.
- **Rotate and flip:** Rotate images manually or use their EXIF orientation information.

### Organize photographs and manage metadata

- **Manage privacy and metadata:** Remove GPS coordinates, AI-related metadata, or all embedded metadata. Choose what to remove while retaining other useful information.
- **Manage photo dates:** Rename photographs using their EXIF dates, shift capture timestamps to correct camera clock errors, and synchronize EXIF and filesystem timestamps.
- **Update copyright information:** Add or modify copyright metadata across multiple photographs.
- **Control what gets preserved:** Choose appropriate metadata and output behavior for different operations.

### Create and share

- **Email photographs:** Send original images or create smaller copies suitable for email attachments.
- **Build photo galleries:** Generate HTML galleries from selected photographs.
- **Create collages:** Arrange multiple images into a single composition.
- **Create PDF albums and print layouts:** Prepare photographs for viewing or printing.
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

Most resizing, compression, and conversion actions let you choose whether to create a new file or overwrite an existing one. **Choose Create new to preserve the original** when that option is available. Web exports, email copies, and video utilities create separate output files.

Some operations, including rotation, flipping, and metadata editing, modify the selected files directly. Rename operations have their own file-handling options.

See [Getting Started](docs/GETTING_STARTED.md) for examples and [Safe Handling](docs/commandconfig.md#output-and-file-handling) for details.

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

- [Getting Started](docs/GETTING_STARTED.md) — Common tasks and examples.
- [User Manual](docs/index.html) — Using KIM6's image and video tools.
- [Complete Action List](docs/ACTIONS.md) — Available Dolphin menu actions.
- [Supported Formats](docs/FORMATS.md) — Image and video format support.
- [Configuration](docs/commandconfig.md) — Customizing KIM6's behavior.
- [Development](DEVELOPMENT.md) — Technical information and contributing.

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