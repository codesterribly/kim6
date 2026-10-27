
# KIM6 Dolphin Menu Actions

KIM6 provides 108 Dolphin menu entries across five service-menu files. This document lists each entry, its menu label, and the command it executes.

The tables reflect the menu definitions in `src/`. Some commands, such as Manual, License, and About, appear in more than one menu.

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
- **Rotate, EXIF auto-orient, flip and flop:** These are in-place operations. `KIM_POLICY=create` refuses them; `prompt` requires explicit two-stage confirmation before any selected original is replaced.
- **Metadata and date operations:** Follow their specific create, overwrite, or timestamp-handling rules.
- **Galleries, collages, albums, and animations:** Create separate output files or directories.
- **Video utilities and slideshows:** Create separate results. Video transcoding also supports authorized overwriting.

For detailed command options, dependencies, and output behavior, see [commandconfig.md](commandconfig.md). For file preservation and overwrite protections, see [File handling](commandconfig.md#output-and-file-handling).

**File-safety choices:** Only `KIM_POLICY=create` and `KIM_POLICY=prompt` are supported. Unset, invalid, or legacy `overwrite` values use the safe prompt, **not** automatic permission. The choice defaults to **Create new files (recommended; originals untouched)**; choosing **Review overwrite options...** requires a second confirmation with an operation-specific label and selected-file count. Cancellation or an unavailable dialog refuses replacement. Destination collisions use distinct names in create mode; destructive publication is checked for source aliases, symlinks, hardlinks, and destination identity as applicable. Batch results already completed are not undone by later failures.

**Format notes:** Animated APNG conversion uses a dedicated FFmpeg path; Resize and Web Export refuse animated APNG instead of silently flattening it. The Convert, Resize, Web Export, and video actions also check format-specific capabilities and output integrity before publication. The action table below is an exact menu mapping, not a guarantee that every installed codec supports every input.

## Complete Menu Action Reference

The following tables list all 108 entries from KIM6's five Dolphin service-menu files.

Each entry includes its internal action ID, the English menu label, and the command defined in the source template. Translated installations may display different labels.

During installation, the `kim_all` command is replaced with the full path to the installed executable. The `%F` placeholder is expanded by Dolphin into the selected filenames.

The mappings are checked against the menu templates by `tests/test_documentation.py`.

### `kim_compress.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Compress10` | JPEG quality: 10% | `kim_all compress --quality 10 -- %F` |
| `Compress30` | JPEG quality: 30% | `kim_all compress --quality 30 -- %F` |
| `Compress50` | JPEG quality: 50% | `kim_all compress --quality 50 -- %F` |
| `Compress70` | JPEG quality: 70% | `kim_all compress --quality 70 -- %F` |
| `Compress90` | JPEG quality: 90% | `kim_all compress --quality 90 -- %F` |
| `CompressCustom` | Compress at custom quality… | `kim_all compress --custom -- %F` |

### `kim_compressandresize.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Resize300` | Resize (300x300 pixels) | `kim_all resize --size 300x300 -- %F` |
| `Resize600` | Resize (600x600 pixels) | `kim_all resize --size 600x600 -- %F` |
| `Resize800` | Resize (800x800 pixels) | `kim_all resize --size 800x800 -- %F` |
| `Resize1024` | Resize (1024x1024 pixels) | `kim_all resize --size 1024x1024 -- %F` |
| `Resize1280` | Resize (1280x1280 pixels) | `kim_all resize --size 1280x1280 -- %F` |
| `Resize1400` | Resize (1400x1400 pixels) | `kim_all resize --size 1400x1400 -- %F` |
| `Resize1600` | Resize (1600x1600 pixels) | `kim_all resize --size 1600x1600 -- %F` |
| `Resize1920` | Resize (1920x1920 pixels) | `kim_all resize --size 1920x1920 -- %F` |
| `Resize2560` | Resize (2560x2560 pixels) | `kim_all resize --size 2560x2560 -- %F` |
| `Resize3440` | Resize (3440x3440 pixels) | `kim_all resize --size 3440x3440 -- %F` |
| `Resize3840` | Resize (3840x3840 pixels) | `kim_all resize --size 3840x3840 -- %F` |
| `ResizeCustom` | Resize custom… | `kim_all resize --custom -- %F` |
| `ResizePercent` | Resize by percentage… | `kim_all resize --custom-percent -- %F` |
| `Web128` | Web thumbnail: 128x128 at 75 % | `kim_all webexport --size 128x128 --quality 75 -- %F` |
| `Web600` | Web export: 600x600 at 75 % | `kim_all webexport --size 600x600 --quality 75 -- %F` |
| `Web800` | Web export: 800x800 at 75 % | `kim_all webexport --size 800x800 --quality 75 -- %F` |
| `Web1024` | Web export: 1024x1024 at 75 % | `kim_all webexport --size 1024x1024 --quality 75 -- %F` |
| `Web1600` | Web export: 1600x1600 at 75 % | `kim_all webexport --size 1600x1600 --quality 75 -- %F` |
| `WebKeep` | Web export, keep input format… | `kim_all webexport --size 1600x1600 --quality 75 --format keep -- %F` |
| `Emailfull` | Send by mail: Send original by mail | `kim_all resizeandsend --size full -- %F` |
| `Email1600x1600` | Send by mail: Resize to 1600px and email | `kim_all resizeandsend --size 1600x1600 -- %F` |
| `Email1200x1200` | Send by mail: Resize to 1200px and email | `kim_all resizeandsend --size 1200x1200 -- %F` |
| `Email800x800` | Send by mail: Resize to 800px and email | `kim_all resizeandsend --size 800x800 -- %F` |
| `Email600x600` | Send by mail: Resize to 600px and email | `kim_all resizeandsend --size 600x600 -- %F` |
| `Email300x300` | Send by mail: Resize to 300px and email | `kim_all resizeandsend --size 300x300 -- %F` |

### `kim_compressandresizevideo.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Videohd72017265orig` | Transcode 720 good H.265 (original container) | `kim_all video --size hd720 --crf 17 --codec libx265 --container orig -- %F` |
| `Videohd72017265mp4` | Transcode 720 good H.265 (MP4) | `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F` |
| `Videohd72017264orig` | Transcode 720 good H.264 (original container) | `kim_all video --size hd720 --crf 17 --codec libx264 --container orig -- %F` |
| `Videohd72017264mp4` | Transcode 720 good H.264 (MP4) | `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F` |
| `Videohd72023265orig` | Transcode 720 medium H.265 (original container) | `kim_all video --size hd720 --crf 23 --codec libx265 --container orig -- %F` |
| `Videohd72023265mp4` | Transcode 720 medium H.265 (MP4) | `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F` |
| `Videohd72023264orig` | Transcode 720 medium H.264 (original container) | `kim_all video --size hd720 --crf 23 --codec libx264 --container orig -- %F` |
| `Videohd72023264mp4` | Transcode 720 medium H.264 (MP4) | `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F` |
| `Videohd72029265orig` | Transcode 720 smaller file H.265 (original container) | `kim_all video --size hd720 --crf 29 --codec libx265 --container orig -- %F` |
| `Videohd72029265mp4` | Transcode 720 smaller file H.265 (MP4) | `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F` |
| `Videohd72029264orig` | Transcode 720 smaller file H.264 (original container) | `kim_all video --size hd720 --crf 29 --codec libx264 --container orig -- %F` |
| `Videohd72029264mp4` | Transcode 720 smaller file H.264 (MP4) | `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F` |
| `Videohd108017265orig` | Transcode 1080 good H.265 (original container) | `kim_all video --size hd1080 --crf 17 --codec libx265 --container orig -- %F` |
| `Videohd108017265mp4` | Transcode 1080 good H.265 (MP4) | `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F` |
| `Videohd108017264orig` | Transcode 1080 good H.264 (original container) | `kim_all video --size hd1080 --crf 17 --codec libx264 --container orig -- %F` |
| `Videohd108017264mp4` | Transcode 1080 good H.264 (MP4) | `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F` |
| `Videohd108023265orig` | Transcode 1080 medium H.265 (original container) | `kim_all video --size hd1080 --crf 23 --codec libx265 --container orig -- %F` |
| `Videohd108023265mp4` | Transcode 1080 medium H.265 (MP4) | `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F` |
| `Videohd108023264orig` | Transcode 1080 medium H.264 (original container) | `kim_all video --size hd1080 --crf 23 --codec libx264 --container orig -- %F` |
| `Videohd108023264mp4` | Transcode 1080 medium H.264 (MP4) | `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F` |
| `Videohd108029265orig` | Transcode 1080 smaller file H.265 (original container) | `kim_all video --size hd1080 --crf 29 --codec libx265 --container orig -- %F` |
| `Videohd108029265mp4` | Transcode 1080 smaller file H.265 (MP4) | `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F` |
| `Videohd108029264orig` | Transcode 1080 smaller file H.264 (original container) | `kim_all video --size hd1080 --crf 29 --codec libx264 --container orig -- %F` |
| `Videohd108029264mp4` | Transcode 1080 smaller file H.264 (MP4) | `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F` |
| `Av1hd720High` | AV1 720p high quality | `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F` |
| `Av1hd720Balanced` | AV1 720p balanced | `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `Av1hd1080High` | AV1 1080p high quality | `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F` |
| `Av1hd1080Balanced` | AV1 1080p balanced | `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `Av1Custom` | Custom AV1 settings… | `kim_all video --size hd1080 --codec av1 --av1-quality custom --container mp4 -- %F` |
| `VideoFrameAt` | Extract frame at timestamp… | `kim_all videoframes --mode single --format png --interactive -- %F` |
| `VideoThumbnail` | Extract automatic thumbnail | `kim_all videoframes --mode thumbnail --format jpg -- %F` |
| `VideoContactSheet` | Create video contact sheet… | `kim_all videoframes --mode contact --format jpg --interactive -- %F` |
| `ExtractVideoAudio` | Extract audio… | `kim_all videoaudio --mode extract --format m4a --interactive -- %F` |
| `MuteVideo` | Remove audio (copy video) | `kim_all videoaudio --mode mute -- %F` |
| `VideoToGif` | Create animated GIF from video… | `kim_all videogif --interactive -- %F` |
| `Manual` | KIM6 Manual | `kim_all manual` |
| `License` | License | `kim_all license` |
| `About` | About KIM6 | `kim_all about` |

### `kim_convertandrotate.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `ConvertJPG` | Convert to JPEG | `kim_all convert --format jpg -- %F` |
| `ConvertPNG` | Convert to PNG | `kim_all convert --format png -- %F` |
| `ConvertGIF` | Convert to GIF | `kim_all convert --format gif -- %F` |
| `ConvertBMP` | Convert to BMP5 bitmap | `kim_all convert --format bmp --bmp5 -- %F` |
| `ConvertTIFF` | Convert to TIFF | `kim_all convert --format tiff -- %F` |
| `ConvertPDF` | Convert to PDF | `kim_all convert --format pdf -- %F` |
| `ConvertWEBP` | Convert to WebP | `kim_all convert --format webp -- %F` |
| `ConvertAVIF` | Convert to AVIF | `kim_all convert --format avif -- %F` |
| `ConvertHEIC` | Convert to HEIC/HEIF | `kim_all convert --format heic -- %F` |
| `ConvertJXL` | Convert to JPEG XL | `kim_all convert --format jxl -- %F` |
| `ConvertJP2Lossless` | Convert to JPEG 2000 (lossless) | `kim_all convert --format jp2 --jp2-mode lossless -- %F` |
| `ConvertJP2Lossy` | Convert to JPEG 2000 (lossy) | `kim_all convert --format jp2 --jp2-mode lossy -- %F` |
| `ConvertCustom` | Convert to custom format… | `kim_all convert --custom-format -- %F` |
| `Rotateexif` | Auto-rotate using EXIF | `kim_all rotate --exif -- %F` |
| `Rotate90` | Rotate 90° | `kim_all rotate --angle 90 -- %F` |
| `Rotate180` | Rotate 180° | `kim_all rotate --angle 180 -- %F` |
| `Rotate270` | Rotate 270° | `kim_all rotate --angle 270 -- %F` |
| `RotateCustom` | Rotate custom angle… | `kim_all rotate --custom -- %F` |
| `FlipVertical` | Flip vertically | `kim_all flipflop flip -- %F` |
| `FlipHorizontal` | Flip horizontally | `kim_all flipflop flop -- %F` |

### `kim_publication.desktop.in`

| Action ID | Menu label | Command |
|---|---|---|
| `Gallery` | Create an HTML gallery… | `kim_all gallery -- %F` |
| `Collage` | Create a photo collage… | `kim_all pelemele -- %F` |
| `Rename` | Rename images… | `kim_all rename interactive -- %F` |
| `SortByDate` | Rename by EXIF date… | `kim_all rename exifdate -- %F` |
| `StripMetadata` | Strip metadata… | `kim_all stripmeta -- %F` |
| `StripGPS` | Remove GPS coordinates… | `kim_all stripmeta --mode gps -- %F` |
| `RemoveAIMetadata` | Remove recognized AI metadata… | `kim_all stripmeta --mode ai -- %F` |
| `SetCopyright` | Set creator and copyright… | `kim_all copyright --interactive -- %F` |
| `AdjustCaptureTime` | Adjust camera timestamps… | `kim_all timeshift --interactive -- %F` |
| `DateSync` | Synchronize photo/file dates… | `kim_all datesync --interactive -- %F` |
| `Slideshow` | Create MP4 slideshow… | `kim_all slideshow --interactive -- %F` |
| `Album` | Create a PDF album… | `kim_all album -- %F` |
| `ContactSheet` | Create a photo contact sheet… | `kim_all contactsheet -- %F` |
| `Print` | Create a print-layout PDF… | `kim_all print -- %F` |
| `TiffJoin` | Join images into a multi-page TIFF… | `kim_all tiffjoin -- %F` |
| `Animation` | Create an animated GIF… | `kim_all animate -- %F` |
| `Manual` | KIM6 Manual | `kim_all manual` |
| `License` | License | `kim_all license` |
| `About` | About KIM6 | `kim_all about` |
