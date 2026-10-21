# Installing KIM6

KIM6 installs one executable runtime entry point, `kim_all`, and five KDE Dolphin service menus, including a JPEG-only compression menu. The original `kim_*` sources remain in the repository as historical references; the installer does not install them as active commands. Gallery templates, the manual, license, About text, and compiled translations are installed beside the dispatcher.

## Runtime requirements

- KDE Plasma 6 / KIO / Dolphin, KDialog, and `qdbus` for progress and cancellation.
- ImageMagick (`magick`, with the formats/codecs you use) for image, PDF, TIFF, GIF, gallery, and collage workflows.
- ExifTool for metadata removal and EXIF-date naming.
- FFmpeg and `ffprobe`; the `libx264` and `libx265` encoders for video presets.
- `xdg-email` for mail handoff and `xdg-open` for the manual, license, and gallery browser workflow.
- `intltool-merge` to render service-menu templates when installing from a source checkout. `msgfmt` is optional; without it menus run in English.

Missing optional codecs or tools cause the related action to report an error; KIM6 does not silently switch output formats or codecs.

## Install or upgrade

From a checkout:

```sh
./install.sh
```

To install into a disposable or nonstandard service-menu directory:

```sh
./install.sh --prefix /path/to/kio/servicemenus
```

The default user installation uses `${XDG_DATA_HOME:-~/.local/share}/kio/servicemenus`. A root installation uses the first configured XDG data directory (normally `/usr/local/share`). The script creates missing directories.

The installer renders and validates all replacement menus and stages the runtime before changing active files. Upgrade recognizes only the five known KIM menu filenames and the `kim6` runtime directory. It refuses a same-named menu that has neither the KIM ownership marker nor a recognizable previous KIM command. It preserves unknown files inside the old runtime tree, and removes a legacy executable only when its contents match the corresponding repository reference. Existing symlinks in the runtime or service-menu targets stop installation safely. If replacement fails, the previous runtime and menu files are restored.

After installation, restart Dolphin or refresh its service-menu cache if the new submenu does not appear. The installer validates staged menus with an isolated `kbuildsycoca6` run when available. After a successful swap, the live cache refresh is best-effort; a refresh failure leaves the installed files in place and can be retried by restarting Dolphin or rebuilding the cache. Customized prior KIM resources that cannot be matched to the previous manifest are retained under a hidden `.kim6-preserved.*` directory inside the runtime tree and are not removed by uninstall.

## Uninstall

```sh
./uninstall.sh
```

Or use `./uninstall.sh --prefix /path/to/kio/servicemenus` for a nonstandard prefix. Uninstall removes only the five named KIM menus when they carry the KIM marker or recognizable old KIM commands. It removes known installed KIM resources individually and leaves unrelated files, even inside the `kim6` resource directory. It will stop if that runtime directory contains symlinks, rather than risk following them.

## Behavior and configuration

- `KIM_POLICY=create` always creates derived outputs. `KIM_POLICY=overwrite` authorizes replacement only for actions that support it; other actions ask before proceeding. Publication uses destination-local staging and the shared safe publication helpers.
- `KIM_NAME_AFFIX_POSITION=prefix|suffix` selects the position of the web, compressed, resized, and stripped filename tags. The KConfig key is `NAME_AFFIX_POSITION`; environment values take precedence and the default is `suffix`.
- `KIM_WEB_FORMAT=jpg|webp|avif|keep` selects web-export encoding, and `KIM_WEB_QUALITY=1..100` supplies its quality prompt default. Web export always creates a separate derived artifact and never replaces a selected source, even under `KIM_POLICY=overwrite`.
- Successful mail-resize attachments are retained under `${XDG_DATA_HOME:-~/.local/share}/kim6/email-attachments` after asynchronous client handoff. Remove those prepared files when they are no longer needed.
- Rotation and metadata stripping preserve source modification timestamps (including available subsecond precision); true rename/move operations preserve filesystem metadata. Compression, conversion, resizing, and flip/flop produce changed content with a fresh modification timestamp. Other derived artifacts receive newly created timestamps.

## Scope

The Dolphin menus route supported image and video workflows through `kim_all`: JPEG compression presets, conversion (including BMP5), resizing, web export, image transformations, metadata removal, EXIF-date and interactive rename, email resizing, PDF albums and print layouts, HTML galleries, collages, TIFF joining, GIF animation, and all 24 video presets. Obsolete Sony multiburst, deprecated basic treatment effects, and obsolete camera-specific downloading are excluded. No other legacy functionality is intentionally excluded.

All menu templates restrict processing to local files and forward selected paths as separate `%F` arguments. Remote URL processing is not supported; KIM6 does not reinterpret URLs as local paths.
