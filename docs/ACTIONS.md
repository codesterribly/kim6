# Action and Dolphin menu inventory

This is the authoritative inventory of the five checked-in service-menu templates. It lists each declared desktop action ID, visible source label, exact `kim_all` command and `%F` selected-file boundary. Count: **107 actions**. The dispatcher accepts additional CLI commands that are not separate menu entries; those are listed in [CLI.md](CLI.md).

## Runtime/action-family matrix

Menu filters: the compression menu is `image/jpeg`; the image, conversion and publication menus are `image/*`; the video menu is `video/*`. All processing menus use `X-KDE-Protocol=file`. Help entries have no file argument. Selected file names are passed by KDE as separate `%F` arguments. Paths containing CR or LF are rejected where the current path-record protocol cannot safely represent them.

“Prompt” means action dialogs are available for interactive menu use; CLI arguments can select settings where the CLI reference documents them. All batch actions use the shared progress/cancellation path unless noted. The source-level test modules listed here contain synthetic real-tool fixtures and/or controlled failure tests for the family.

| Dispatcher action(s) / menu IDs | Prompts and required tools | Output policy, naming, metadata/time | Cancellation and output validation | Regression coverage |
|---|---|---|---|---|
| `compress` — `Compress10/30/50/70/90/Custom` | JPEG only; custom quality and JPEG scan/Huffman choices. ImageMagick. | Create or authorized original replacement; create uses configured `_compressed` affix. Changed pixels receive a fresh mtime. | Shared progress; staged JPEG decode/format/dimensions and profile checks. | `test_compression.py`, `test_affix.py`, `test_cancellation.py` |
| `convert` — `ConvertJPG/PNG/GIF/BMP/TIFF/PDF/WEBP/AVIF/HEIC/JXL/JP2Lossless/JP2Lossy/Custom` | Custom format and applicable JPEG/JP2 options. ImageMagick; FFmpeg/ffprobe for APNG; selected encoders are probed. | Create or authorized replacement of converted target; original input remains protected. | Reject unsupported frame flattening; validate encoding, decode, dimensions, frames and profiles as relevant. | `test_conversion.py`, `test_publication.py` |
| `resize` — `Resize300/600/800/1024/1280/1400/1600/1920/2560/3440/3840/Custom/Percent` | Geometry or 1–1000% prompt/argument. ImageMagick and ExifTool checks. | Create with `_resized` affix or authorized replacement; fresh mtime, existing metadata policy retained. | Cancellation before publication; decoded output/geometry/frame validation. | `test_resize.py`, `test_affix.py`, `test_cancellation.py` |
| `webexport` — `Web128/Web600/Web800/Web1024/Web1600/WebKeep` | Size, quality, format, destination and color mode. ImageMagick, ExifTool; FFmpeg for APNG handling; output encoder/profile resources. | **Always derived-only**, regardless of `KIM_POLICY`; `_web` affix and collision numbering. ICC-managed sRGB is default. | Cancellation before publication; actual encoding, decode, dimensions, orientation, frames and profile validated. | `test_webexport.py`, `test_web_email.py`, `test_affix.py` |
| `resizeandsend` — `Emailfull/Email1600x1600/Email1200x1200/Email800x800/Email600x600/Email300x300` | Size choice; mail handoff. ImageMagick; KMail, Thunderbird or `xdg-email` optional. | Source remains unchanged. Valid prepared images are copied to persistent attachment storage for asynchronous clients. | Per-item output format/dimensions/frames checked; interruption stops batch/handoff. | `test_web_email.py` |
| `rename` — `Rename/SortByDate` | Interactive sequential numbering, destination, text/case/spacing/prefix/suffix or EXIF date format. ExifTool for EXIF dates. | True rename/move or create-copy mode; preserves bytes and filesystem metadata. Whole batch is preflighted. | Cancellation between filesystem operations; no-clobber destinations and source identities checked. | `test_rename.py`, `test_cancellation.py` |
| `rotate`, `rotatewithexif`, `flipflop` — `Rotateexif/Rotate90/Rotate180/Rotate270/RotateCustom/FlipVertical/FlipHorizontal` | Angle prompt for custom rotation. ImageMagick and ExifTool. | Explicitly in-place actions, independent of `KIM_POLICY`; rotation preserves nanosecond mtime, while flip/flop receives a fresh mtime. | Shared cancellation; destination-local stage, full decode, pixels, dimensions, frame count and ICC checks. | `test_transform.py`, `test_cancellation.py` |
| `stripmeta` — `StripMetadata/StripGPS/RemoveAIMetadata` | Interactive metadata scope where requested. ExifTool, ImageMagick. | Create or authorized replacement; original mtime/permissions preserved. Selective GPS/AI modes retain unrelated metadata. | Cancellation before publication; compare pixels, profiles, dimensions, frames and expected tag removal. | `test_stripmeta.py`, `test_metadata_actions.py` |
| `copyright`, `timeshift` — `SetCopyright/AdjustCaptureTime` | Copyright fields/year and signed camera-time shift; before/after preview. ExifTool, ImageMagick. | Metadata-only; create or authorized replacement; no pixel recompression; filesystem mtime preserved. | Shared cancellation and staged metadata/tag validation. | `test_metadata_actions.py` |
| `datesync` — `DateSync` | Direction and, for file-to-EXIF, fields. ExifTool; ImageMagick for embedded edits. | EXIF-to-file changes mtime or creates a byte-identical copy; file-to-EXIF is metadata-only and preserves mtime. | Preview/confirmation; validates date fields, precision and unchanged pixels/metadata as appropriate. | `test_datesync.py`, `test_metadata_actions.py` |
| `gallery`, `pelemele` — `Gallery/Collage` | Gallery title/author/layout/output directory; collage canvas, tile, overlap, colors, border, rotation/shadow/output. ImageMagick; `xdg-open` for browser. | New derived directory or image; do not replace occupied gallery directories or selected sources. | Stage/validate complete gallery tree or collage bytes before publication; cancellation prevents publication. | `test_gallery_collage.py` |
| `album`, `print`, `tiffjoin`, `animate` — `Album/Print/TiffJoin/Animation` | Eight album layouts; seven print layouts; output selection; GIF delay/loop. ImageMagick. | Derived PDF/TIFF/GIF, with create/authorized destination policy; selected inputs are never modified. GIF delay defaults to 100 centiseconds; loop defaults to infinite. | Destination-local staging; validates pages/layouts, encoding, frames, timing, and collisions. | `test_publications.py`, `test_publication.py` |
| `video` — 24 H.264/H.265 presets, five AV1 entries | Preset arguments or custom AV1 settings. FFmpeg/ffprobe; chosen encoder required. | Create or explicitly authorized replacement; codec/container selection is never silently changed. | Owned FFmpeg process cancellation; probe, stream, duration, dimensions and full-decode validation. | `test_video.py`, `test_cancellation.py` |
| `videoframes`, `videoaudio`, `videogif` — six video utility entries | Timestamp/grid/format, audio format, or GIF interval/fps/width/loop prompts. FFmpeg/ffprobe; ImageMagick for contact-sheet composition. | Derived-only frame, contact sheet, audio, muted video, or GIF; source is never replaced. | Owned-process cancellation; validate stream/frame count, format, timing, dimensions and full decode. | `test_video_utilities.py` |
| `slideshow` — `Slideshow` | Duration per image, size, fps, background, output path. ImageMagick, ExifTool, FFmpeg/ffprobe, `setsid`, `libx264`, ICC resources where needed. | Always creates a derived H.264 MP4; natural filename order; no audio. | Stops only invocation-owned producers; validates sequence, codec, dimensions, frame rate, duration and full decode. | `test_slideshow.py` |
| `about`, `license`, `manual` — contextual entries in Video and Publication menus | About dialog or open installed resource; KDialog and `xdg-open`. | No media output. | Reports missing installed resource/open failure. | `test_unified_integration.py` |

The shared publication contract promises atomic visibility on supported local filesystems, not crash durability or protection from arbitrary external writers. See [SAFETY.md](SAFETY.md) for the precise limits.
## Complete menu action mapping

The following rows are generated from the current menu templates and are kept in sync by `test_documentation.py`. The command is the template command; installation substitutes the absolute installed dispatcher path.

### `kim_compress.desktop.in`

| Template | Menu ID | Visible label | Template Exec |
|---|---|---|---|
| `kim_compress.desktop.in` | `Compress10` | JPEG quality: 10% | `kim_all compress --quality 10 -- %F` |
| `kim_compress.desktop.in` | `Compress30` | JPEG quality: 30% | `kim_all compress --quality 30 -- %F` |
| `kim_compress.desktop.in` | `Compress50` | JPEG quality: 50% | `kim_all compress --quality 50 -- %F` |
| `kim_compress.desktop.in` | `Compress70` | JPEG quality: 70% | `kim_all compress --quality 70 -- %F` |
| `kim_compress.desktop.in` | `Compress90` | JPEG quality: 90% | `kim_all compress --quality 90 -- %F` |
| `kim_compress.desktop.in` | `CompressCustom` | Compress at custom quality… | `kim_all compress --custom -- %F` |

### `kim_compressandresize.desktop.in`

| Template | Menu ID | Visible label | Template Exec |
|---|---|---|---|
| `kim_compressandresize.desktop.in` | `Resize300` | Resize (300x300 pixels) | `kim_all resize --size 300x300 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize600` | Resize (600x600 pixels) | `kim_all resize --size 600x600 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize800` | Resize (800x800 pixels) | `kim_all resize --size 800x800 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize1024` | Resize (1024x1024 pixels) | `kim_all resize --size 1024x1024 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize1280` | Resize (1280x1280 pixels) | `kim_all resize --size 1280x1280 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize1400` | Resize (1400x1400 pixels) | `kim_all resize --size 1400x1400 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize1600` | Resize (1600x1600 pixels) | `kim_all resize --size 1600x1600 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize1920` | Resize (1920x1920 pixels) | `kim_all resize --size 1920x1920 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize2560` | Resize (2560x2560 pixels) | `kim_all resize --size 2560x2560 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize3440` | Resize (3440x3440 pixels) | `kim_all resize --size 3440x3440 -- %F` |
| `kim_compressandresize.desktop.in` | `Resize3840` | Resize (3840x3840 pixels) | `kim_all resize --size 3840x3840 -- %F` |
| `kim_compressandresize.desktop.in` | `ResizeCustom` | Resize custom… | `kim_all resize --custom -- %F` |
| `kim_compressandresize.desktop.in` | `ResizePercent` | Resize by percentage… | `kim_all resize --custom-percent -- %F` |
| `kim_compressandresize.desktop.in` | `Web128` | Web thumbnail: 128x128 at 75 % | `kim_all webexport --size 128x128 --quality 75 -- %F` |
| `kim_compressandresize.desktop.in` | `Web600` | Web export: 600x600 at 75 % | `kim_all webexport --size 600x600 --quality 75 -- %F` |
| `kim_compressandresize.desktop.in` | `Web800` | Web export: 800x800 at 75 % | `kim_all webexport --size 800x800 --quality 75 -- %F` |
| `kim_compressandresize.desktop.in` | `Web1024` | Web export: 1024x1024 at 75 % | `kim_all webexport --size 1024x1024 --quality 75 -- %F` |
| `kim_compressandresize.desktop.in` | `Web1600` | Web export: 1600x1600 at 75 % | `kim_all webexport --size 1600x1600 --quality 75 -- %F` |
| `kim_compressandresize.desktop.in` | `WebKeep` | Web export, keep input format… | `kim_all webexport --size 1600x1600 --quality 75 --format keep -- %F` |
| `kim_compressandresize.desktop.in` | `Emailfull` | Send by mail: Send original by mail | `kim_all resizeandsend --size full -- %F` |
| `kim_compressandresize.desktop.in` | `Email1600x1600` | Send by mail: Resize to 1600px and email | `kim_all resizeandsend --size 1600x1600 -- %F` |
| `kim_compressandresize.desktop.in` | `Email1200x1200` | Send by mail: Resize to 1200px and email | `kim_all resizeandsend --size 1200x1200 -- %F` |
| `kim_compressandresize.desktop.in` | `Email800x800` | Send by mail: Resize to 800px and email | `kim_all resizeandsend --size 800x800 -- %F` |
| `kim_compressandresize.desktop.in` | `Email600x600` | Send by mail: Resize to 600px and email | `kim_all resizeandsend --size 600x600 -- %F` |
| `kim_compressandresize.desktop.in` | `Email300x300` | Send by mail: Resize to 300px and email | `kim_all resizeandsend --size 300x300 -- %F` |

### `kim_compressandresizevideo.desktop.in`

| Template | Menu ID | Visible label | Template Exec |
|---|---|---|---|
| `kim_compressandresizevideo.desktop.in` | `Videohd72017265orig` | Transcode 720 good H.265 (original container) | `kim_all video --size hd720 --crf 17 --codec libx265 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72017265mp4` | Transcode 720 good H.265 (MP4) | `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72017264orig` | Transcode 720 good H.264 (original container) | `kim_all video --size hd720 --crf 17 --codec libx264 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72017264mp4` | Transcode 720 good H.264 (MP4) | `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72023265orig` | Transcode 720 medium H.265 (original container) | `kim_all video --size hd720 --crf 23 --codec libx265 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72023265mp4` | Transcode 720 medium H.265 (MP4) | `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72023264orig` | Transcode 720 medium H.264 (original container) | `kim_all video --size hd720 --crf 23 --codec libx264 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72023264mp4` | Transcode 720 medium H.264 (MP4) | `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72029265orig` | Transcode 720 smaller file H.265 (original container) | `kim_all video --size hd720 --crf 29 --codec libx265 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72029265mp4` | Transcode 720 smaller file H.265 (MP4) | `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72029264orig` | Transcode 720 smaller file H.264 (original container) | `kim_all video --size hd720 --crf 29 --codec libx264 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd72029264mp4` | Transcode 720 smaller file H.264 (MP4) | `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108017265orig` | Transcode 1080 good H.265 (original container) | `kim_all video --size hd1080 --crf 17 --codec libx265 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108017265mp4` | Transcode 1080 good H.265 (MP4) | `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108017264orig` | Transcode 1080 good H.264 (original container) | `kim_all video --size hd1080 --crf 17 --codec libx264 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108017264mp4` | Transcode 1080 good H.264 (MP4) | `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108023265orig` | Transcode 1080 medium H.265 (original container) | `kim_all video --size hd1080 --crf 23 --codec libx265 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108023265mp4` | Transcode 1080 medium H.265 (MP4) | `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108023264orig` | Transcode 1080 medium H.264 (original container) | `kim_all video --size hd1080 --crf 23 --codec libx264 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108023264mp4` | Transcode 1080 medium H.264 (MP4) | `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108029265orig` | Transcode 1080 smaller file H.265 (original container) | `kim_all video --size hd1080 --crf 29 --codec libx265 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108029265mp4` | Transcode 1080 smaller file H.265 (MP4) | `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108029264orig` | Transcode 1080 smaller file H.264 (original container) | `kim_all video --size hd1080 --crf 29 --codec libx264 --container orig -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Videohd108029264mp4` | Transcode 1080 smaller file H.264 (MP4) | `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Av1hd720High` | AV1 720p high quality | `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Av1hd720Balanced` | AV1 720p balanced | `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Av1hd1080High` | AV1 1080p high quality | `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Av1hd1080Balanced` | AV1 1080p balanced | `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Av1Custom` | Custom AV1 settings… | `kim_all video --size hd1080 --codec av1 --av1-quality custom --container mp4 -- %F` |
| `kim_compressandresizevideo.desktop.in` | `VideoFrameAt` | Extract frame at timestamp… | `kim_all videoframes --mode single --format png --interactive -- %F` |
| `kim_compressandresizevideo.desktop.in` | `VideoThumbnail` | Extract automatic thumbnail | `kim_all videoframes --mode thumbnail --format jpg -- %F` |
| `kim_compressandresizevideo.desktop.in` | `VideoContactSheet` | Create video contact sheet… | `kim_all videoframes --mode contact --format jpg --interactive -- %F` |
| `kim_compressandresizevideo.desktop.in` | `ExtractVideoAudio` | Extract audio… | `kim_all videoaudio --mode extract --format m4a --interactive -- %F` |
| `kim_compressandresizevideo.desktop.in` | `MuteVideo` | Remove audio (copy video) | `kim_all videoaudio --mode mute -- %F` |
| `kim_compressandresizevideo.desktop.in` | `VideoToGif` | Create animated GIF from video… | `kim_all videogif --interactive -- %F` |
| `kim_compressandresizevideo.desktop.in` | `Manual` | KIM6 Manual | `kim_all manual` |
| `kim_compressandresizevideo.desktop.in` | `License` | License | `kim_all license` |
| `kim_compressandresizevideo.desktop.in` | `About` | About KIM6 | `kim_all about` |

### `kim_convertandrotate.desktop.in`

| Template | Menu ID | Visible label | Template Exec |
|---|---|---|---|
| `kim_convertandrotate.desktop.in` | `ConvertJPG` | Convert to JPEG | `kim_all convert --format jpg -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertPNG` | Convert to PNG | `kim_all convert --format png -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertGIF` | Convert to GIF | `kim_all convert --format gif -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertBMP` | Convert to BMP5 bitmap | `kim_all convert --format bmp --bmp5 -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertTIFF` | Convert to TIFF | `kim_all convert --format tiff -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertPDF` | Convert to PDF | `kim_all convert --format pdf -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertWEBP` | Convert to WebP | `kim_all convert --format webp -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertAVIF` | Convert to AVIF | `kim_all convert --format avif -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertHEIC` | Convert to HEIC/HEIF | `kim_all convert --format heic -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertJXL` | Convert to JPEG XL | `kim_all convert --format jxl -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertJP2Lossless` | Convert to JPEG 2000 (lossless) | `kim_all convert --format jp2 --jp2-mode lossless -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertJP2Lossy` | Convert to JPEG 2000 (lossy) | `kim_all convert --format jp2 --jp2-mode lossy -- %F` |
| `kim_convertandrotate.desktop.in` | `ConvertCustom` | Convert to custom format… | `kim_all convert --custom-format -- %F` |
| `kim_convertandrotate.desktop.in` | `Rotateexif` | Auto-rotate using EXIF | `kim_all rotate --exif -- %F` |
| `kim_convertandrotate.desktop.in` | `Rotate90` | Rotate 90° | `kim_all rotate --angle 90 -- %F` |
| `kim_convertandrotate.desktop.in` | `Rotate180` | Rotate 180° | `kim_all rotate --angle 180 -- %F` |
| `kim_convertandrotate.desktop.in` | `Rotate270` | Rotate 270° | `kim_all rotate --angle 270 -- %F` |
| `kim_convertandrotate.desktop.in` | `RotateCustom` | Rotate custom angle… | `kim_all rotate --custom -- %F` |
| `kim_convertandrotate.desktop.in` | `FlipVertical` | Flip vertically | `kim_all flipflop flip -- %F` |
| `kim_convertandrotate.desktop.in` | `FlipHorizontal` | Flip horizontally | `kim_all flipflop flop -- %F` |

### `kim_publication.desktop.in`

| Template | Menu ID | Visible label | Template Exec |
|---|---|---|---|
| `kim_publication.desktop.in` | `Gallery` | Create an HTML gallery… | `kim_all gallery -- %F` |
| `kim_publication.desktop.in` | `Collage` | Create a photo collage… | `kim_all pelemele -- %F` |
| `kim_publication.desktop.in` | `Rename` | Rename images… | `kim_all rename interactive -- %F` |
| `kim_publication.desktop.in` | `SortByDate` | Rename by EXIF date… | `kim_all rename exifdate -- %F` |
| `kim_publication.desktop.in` | `StripMetadata` | Strip metadata… | `kim_all stripmeta -- %F` |
| `kim_publication.desktop.in` | `StripGPS` | Remove GPS coordinates… | `kim_all stripmeta --mode gps -- %F` |
| `kim_publication.desktop.in` | `RemoveAIMetadata` | Remove recognized AI metadata… | `kim_all stripmeta --mode ai -- %F` |
| `kim_publication.desktop.in` | `SetCopyright` | Set creator and copyright… | `kim_all copyright --interactive -- %F` |
| `kim_publication.desktop.in` | `AdjustCaptureTime` | Adjust camera timestamps… | `kim_all timeshift --interactive -- %F` |
| `kim_publication.desktop.in` | `DateSync` | Synchronize photo/file dates… | `kim_all datesync --interactive -- %F` |
| `kim_publication.desktop.in` | `Slideshow` | Create MP4 slideshow… | `kim_all slideshow --interactive -- %F` |
| `kim_publication.desktop.in` | `Album` | Create a PDF album… | `kim_all album -- %F` |
| `kim_publication.desktop.in` | `Print` | Create a print-layout PDF… | `kim_all print -- %F` |
| `kim_publication.desktop.in` | `TiffJoin` | Join images into a multi-page TIFF… | `kim_all tiffjoin -- %F` |
| `kim_publication.desktop.in` | `Animation` | Create an animated GIF… | `kim_all animate -- %F` |
| `kim_publication.desktop.in` | `Manual` | KIM6 Manual | `kim_all manual` |
| `kim_publication.desktop.in` | `License` | License | `kim_all license` |
| `kim_publication.desktop.in` | `About` | About KIM6 | `kim_all about` |
