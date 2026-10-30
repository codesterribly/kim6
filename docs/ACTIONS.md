
# KIM6 Dolphin Menu Actions

KIM6 provides 82 executable Dolphin actions across ten service-menu files. This document lists each entry, its menu label, and the command it executes.

The tables reflect the menu definitions in `src/`. Settings, Manual, License, and About are grouped in the dedicated information service menu.

For command-line options beyond those available through Dolphin, see [commandconfig.md](commandconfig.md).

## Menu Behavior

Dolphin displays KIM6 actions according to the selected file type:

- **JPEG compression:** JPEG images.
- **Image processing and publication:** Supported image files.
- **Video processing:** Supported video files.

The menu definitions use `X-KDE-Protocol=file` for local files. Dolphin passes selected filenames through `%F`, allowing actions to process multiple files.

File handling depends on the operation:

- **Resize, compress, and convert:** Create new files or overwrite existing files when authorized.
- **Web export and email:** Create separate output files without changing the selected images.
- **Rotate, EXIF auto-orient, flip and flop:** Create mode publishes transformed copies and preserves selected originals. Overwrite mode replaces selected originals only after explicit two-stage confirmation.
- **Metadata and date operations:** Follow their specific create, overwrite, or timestamp-handling rules.
- **Galleries, collages, albums, and animations:** Create separate output files or directories.
- **Video utilities and slideshows:** Create separate results. Video transcoding also supports authorized overwriting.

For detailed command options, dependencies, and output behavior, see [commandconfig.md](commandconfig.md). For file preservation and overwrite protections, see [File handling](commandconfig.md#output-and-file-handling).

**File-safety choices:** `KIM_POLICY=create` selects separate outputs where supported; `KIM_POLICY=prompt` displays the output-policy dialog. Create is the default choice. Choosing **Overwrite originals (confirmation required)** requires a second confirmation with an operation-specific warning and selected-file count. Cancellation or an unavailable dialog refuses replacement. Create mode numbers output collisions; publication checks source aliases, symlinks, hardlinks, and destination identity where applicable. Completed batch results remain available if a later item fails.

**Format notes:** Animated APNG conversion uses a dedicated FFmpeg path; Resize and Web Export refuse animated APNG instead of silently flattening it. The Convert, Resize, Web Export, and video actions also check format-specific capabilities and output integrity before publication. The action table below is an exact menu mapping, not a guarantee that every installed codec supports every input.

## Complete Menu Action Reference

The following tables list all 82 executable actions from KIM6's ten Dolphin service-menu files.

Each entry includes its internal action ID, the English menu label, and the command defined in the source template. Translated installations may display different labels.

During installation, the `kim_all` command is replaced with the full path to the installed executable. The `%F` placeholder is expanded by Dolphin into the selected filenames.

The mappings are checked against the menu templates by `tests/test_documentation.py`.

### `kim_compressandresize.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `01Resize1600` | Resize to 1600 × 1600 | `kim_all resize --size 1600x1600 -- %F` |
| `02Resize1280` | Resize to 1280 × 1280 | `kim_all resize --size 1280x1280 -- %F` |
| `03Resize1024` | Resize to 1024 × 1024 | `kim_all resize --size 1024x1024 -- %F` |
| `04ResizePercent` | Resize by Percentage… | `kim_all resize --custom-percent -- %F` |
| `05ResizeCustom` | Resize to Custom Size… | `kim_all resize --custom -- %F` |
| `10Rotate90` | Rotate 90° CW | `kim_all rotate --angle 90 -- %F` |
| `11Rotate270` | Rotate 90° CCW | `kim_all rotate --angle 270 -- %F` |
| `12Rotate180` | Rotate 180° | `kim_all rotate --angle 180 -- %F` |
| `13RotateCustom` | Rotate by Custom Angle… | `kim_all rotate --custom -- %F` |
| `14Rotateexif` | Auto-Rotate Using EXIF | `kim_all rotate --exif -- %F` |
| `20FlipHorizontal` | Flip Horizontally | `kim_all flipflop flop -- %F` |
| `21FlipVertical` | Flip Vertically | `kim_all flipflop flip -- %F` |

### `kim_compressandresizevideo.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Videohd108017265mp4` | 1080p • High Quality • MP4 | `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F` |
| `Videohd108023265mp4` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F` |
| `Videohd108029265mp4` | 1080p • Smallest File • MP4 | `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F` |
| `Videohd72017265mp4` | 720p • High Quality • MP4 | `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F` |
| `Videohd72023265mp4` | 720p • Balanced • MP4 | `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F` |
| `Videohd72029265mp4` | 720p • Smallest File • MP4 | `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F` |

### `kim_convertandrotate.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `01ConvertAVIF` | Convert to AVIF | `kim_all convert --format avif -- %F` |
| `02ConvertBMP` | Convert to BMP | `kim_all convert --format bmp --bmp5 -- %F` |
| `03ConvertGIF` | Convert to GIF | `kim_all convert --format gif -- %F` |
| `04ConvertHEIC` | Convert to HEIC/HEIF | `kim_all convert --format heic -- %F` |
| `05ConvertJP2Lossless` | Convert to JPEG 2000 (Lossless) | `kim_all convert --format jp2 --jp2-mode lossless -- %F` |
| `06ConvertJP2Lossy` | Convert to JPEG 2000 (Lossy) | `kim_all convert --format jp2 --jp2-mode lossy -- %F` |
| `07ConvertJPG` | Convert to JPEG | `kim_all convert --format jpg -- %F` |
| `08ConvertJXL` | Convert to JPEG XL | `kim_all convert --format jxl -- %F` |
| `09ConvertPDF` | Convert to PDF | `kim_all convert --format pdf -- %F` |
| `10ConvertPNG` | Convert to PNG | `kim_all convert --format png -- %F` |
| `11ConvertTIFF` | Convert to TIFF | `kim_all convert --format tiff -- %F` |
| `12ConvertWEBP` | Convert to WebP | `kim_all convert --format webp -- %F` |
| `2001CompressRecommended` | Compress Recommended | `kim_all compress --recommended -- %F` |
| `2102CompressMaximum` | Compress Maximum | `kim_all compress --maximum -- %F` |
| `2203CompressCustom` | Compress Custom | `kim_all compress --custom -- %F` |

### `kim_information.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `01Settings` | Settings… | `kim_all settings` |
| `02About` | About KIM6… | `kim_all about` |
| `03License` | License | `kim_all license` |
| `04Manual` | KIM6 Manual | `kim_all manual` |

### `kim_metadata.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `01Rename` | Rename Images… | `kim_all rename interactive -- %F` |
| `02AdjustCaptureTime` | Adjust camera timestamps… | `kim_all timeshift --interactive -- %F` |
| `03DateSync` | Synchronize photo/file dates… | `kim_all datesync --interactive -- %F` |
| `04SetCopyright` | Set creator and copyright… | `kim_all copyright --interactive -- %F` |
| `05StripMetadata` | Strip Metadata… | `kim_all stripmeta -- %F` |
| `06StripAI` | Strip AI Metadata… | `kim_all stripmeta --mode ai -- %F` |
| `07StripGPS` | Strip GPS Metadata… | `kim_all stripmeta --mode gps -- %F` |

### `kim_publication.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Album` | Create a PDF album… | `kim_all album -- %F` |
| `Animation` | Create an animated GIF… | `kim_all animate -- %F` |
| `Collage` | Create a photo collage… | `kim_all pelemele -- %F` |
| `ContactSheet` | Create a photo contact sheet… | `kim_all contactsheet -- %F` |
| `Gallery` | Create an HTML gallery… | `kim_all gallery -- %F` |
| `Print` | Create a print-layout PDF… | `kim_all print -- %F` |
| `Slideshow` | Create a video slideshow… | `kim_all slideshow --interactive -- %F` |
| `TiffJoin` | Create a multi-page TIFF… | `kim_all tiffjoin -- %F` |
| `Emailfull` | Send via email… | `kim_all resizeandsend --size full -- %F` |

### `kim_video_av1.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Av1hd1080Balanced` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `Av1hd1080High` | 1080p • High Quality • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F` |
| `Av1hd720Balanced` | 720p • Balanced • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `Av1hd720High` | 720p • High Quality • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F` |
| `Av1Custom` | Custom AV1 Settings… | `kim_all video --size hd1080 --codec av1 --av1-quality custom --container mp4 -- %F` |

### `kim_video_h264.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Videohd108017264mp4` | 1080p • High Quality • MP4 | `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F` |
| `Videohd108023264mp4` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F` |
| `Videohd108029264mp4` | 1080p • Smallest File • MP4 | `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F` |
| `Videohd72017264mp4` | 720p • High Quality • MP4 | `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F` |
| `Videohd72023264mp4` | 720p • Balanced • MP4 | `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F` |
| `Videohd72029264mp4` | 720p • Smallest File • MP4 | `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F` |

### `kim_videoutilities.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `ExtractVideoAudio` | Extract audio… | `kim_all videoaudio --mode extract --format m4a --interactive -- %F` |
| `VideoFrameAt` | Extract frame at timestamp… | `kim_all videoframes --mode single --format png --interactive -- %F` |
| `VideoThumbnail` | Extract automatic thumbnail | `kim_all videoframes --mode thumbnail --format jpg -- %F` |
| `MuteVideo` | Remove audio (copy video) | `kim_all videoaudio --mode mute -- %F` |
| `VideoContactSheet` | Create video contact sheet… | `kim_all videoframes --mode contact --format jpg --interactive -- %F` |
| `VideoToGif` | Create animated GIF from video… | `kim_all videogif --interactive -- %F` |

### `kim_webemail.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `0101WebExport` | JPEG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format jpg -- %F` |
| `0102WebExport` | JPEG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format jpg -- %F` |
| `0103WebExport` | JPEG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format jpg -- %F` |
| `0201WebExport` | PNG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format png -- %F` |
| `0202WebExport` | PNG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format png -- %F` |
| `0203WebExport` | PNG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format png -- %F` |
| `0301WebExport` | WebP · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format webp -- %F` |
| `0302WebExport` | WebP · Medium (800 × 800) | `kim_all webexport --size 800x800 --format webp -- %F` |
| `0303WebExport` | WebP · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format webp -- %F` |
| `0401WebExport` | AVIF · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format avif -- %F` |
| `0402WebExport` | AVIF · Medium (800 × 800) | `kim_all webexport --size 800x800 --format avif -- %F` |
| `0403WebExport` | AVIF · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format avif -- %F` |
