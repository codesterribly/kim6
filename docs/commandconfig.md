
# KIM6 Command and Configuration Reference

`kim_all` is KIM6's main executable. Dolphin normally runs it through the service menus, but it can also be called directly from a terminal.

When working from the source directory, use:

```sh
./src/bin/kim_all --help
```

To run a command from the source directory:

```sh
./src/bin/kim_all compress --quality 70 -- photo.jpg
```

The examples below use `kim_all` for readability. Replace it with `./src/bin/kim_all` or the full path to the installed executable when running commands directly.

Separate command options from filenames with `--`. Quote filenames containing spaces or special characters.

Some commands display KDialog prompts when options are omitted. Configuration settings and environment variables can supply defaults; see [Configuration and Defaults](#configuration-and-defaults) below.

For the complete list of Dolphin menu entries, see [ACTIONS.md](ACTIONS.md).

## Contents

- [Command Syntax](#command-syntax)
- [Output and File Handling](#output-and-file-handling)
- [Configuration and Defaults](#configuration-and-defaults)
- [Still-image actions](#still-image-actions): album, animate, collage, compress, contactsheet, convert, copyright, datesync, flipflop, gallery, print, rename, resize, resizeandsend, rotate, rotatewithexif, stripmeta, tiffjoin, timeshift, webexport
- [Video actions](#video-actions): slideshow, video, videoaudio, videoframes, videogif
- [Information actions](#information-actions): about, license, manual, settings

## Command Syntax

Most processing commands follow this structure:

```text
kim_all COMMAND [OPTIONS] -- FILE...
```

- `COMMAND` selects the operation.
- `[OPTIONS]` represents optional or required settings.
- `--` separates command options from filenames.
- `FILE...` represents one or more selected files.

Some commands also accept a destination directory as a positional argument. Those forms are documented under the relevant commands.

The `about`, `license`, and `manual` commands do not require files.

The command blocks below show syntax patterns. Values separated by `|` are alternatives, not literal shell pipelines.

## Output and File Handling

KIM6 uses different file-handling rules depending on the operation.

- **Create new:** Generates a separate file, normally using an action-specific filename suffix. Existing filenames are handled without silently replacing them.
- **Overwrite:** Replaces an existing file only when the operation supports it and replacement is authorized.
- **Derived output:** Always creates a separate result, regardless of `KIM_POLICY`.
- **In-place operation:** Replaces a selected original after explicit authorization. Rotation and flipping support this in Overwrite mode and can instead publish transformed copies.

The output-policy prompt defaults to **Create new files (originals untouched)**. Selecting **Overwrite originals (confirmation required)** requires a second, action-specific warning identifying the selected-file count. Canceling either dialog or losing access to KDialog refuses replacement. Authorization applies to the selected batch.

Some metadata and timestamp operations have additional rules. Each command section describes its applicable behavior.

See [File handling](#output-and-file-handling) for file preservation and overwrite protections. The next section explains how to configure output policies and other defaults.

### File preservation details

Compression, conversion, resizing, and metadata changes support Create or explicitly authorized Overwrite behavior according to the action. Rotation, EXIF auto-orientation, flipping, and flopping can publish separate copies or replace originals after confirmation. Rename preflights conflicts before moving or copying files. Exports, email preparations, extracted video media, slideshows, galleries, and other derived publications preserve selected sources. Video transcoding can replace a selected original after explicit confirmation.

Metadata-only edits do not recompress image pixels. Rotation preserves source modification time, while flipping gives the changed file a fresh modification time. EXIF-to-filesystem date synchronization deliberately changes filesystem modification time; file-to-EXIF synchronization edits embedded timestamps instead. There is no global promise to preserve every metadata field or filesystem timestamp.

Existing destinations are protected by staged validation and publication checks. For symlink, hardlink, cancellation, atomic-replacement and race-condition limitations, see [File publication and cancellation](DEVELOPMENT.md#file-publication-and-cancellation).

For compression, conversion, resizing, metadata stripping and copyright editing, duplicate file identities (including aliases to the same file) cause the entire selection to be rejected before processing. Rotation and flipping instead report a repeated source as a failed item without transforming it again; camera-time shifting skips repeated paths and canonical-parent aliases after a successful update. All these actions reject filenames containing line breaks before processing. A processing failure returns a nonzero exit status even when other files in that batch were completed successfully; already published outputs are retained.

## Configuration and Defaults

**For normal use, open Settings in Dolphin:** Right-click a supported file and choose **Actions → KIM6 — Settings/About → Settings**. Choose whether actions prompt about replacement or automatically create separate copies where supported. The **Output Filenames** tab lets you customize the labels automatically added to output names, choose prefix or suffix placement, and preview examples. You can also set separate JPEG/WebP/AVIF web-export quality defaults and copyright details. Click **Save**. KIM6 reads these settings for subsequent actions; no manual configuration editing or Dolphin restart is required.

### Settings

The graphical Settings dialog writes `${XDG_CONFIG_HOME:-$HOME/.config}/kim6/settings.conf` (normally `~/.config/kim6/settings.conf`). It is a simple validated `KEY=value` text file, **not** KConfig and not an executable shell script. The dispatcher reads supported keys at startup. Explicit environment variables override their corresponding saved values, but cannot authorize overwriting without confirmation.

| Setting / environment variable | Default | Behavior |
|---|---|---|
| `KIM_POLICY` | `prompt` | `prompt` asks for Create or Overwrite where supported. `create` automatically selects separate outputs where supported and prevents actions requiring original-file replacement. |
| `KIM_NAME_AFFIX_POSITION` | `suffix` | Generated name tags appear after (`photo_web.jpg`) or before (`web_photo.jpg`) the filename stem. |
| `KIM_AFFIX_*` | See below | User-configurable labels for automatically generated output filenames. |
| `KIM_WEB_QUALITY_JPEG` | `95` | Default JPEG web-export quality (1–100). |
| `KIM_WEB_QUALITY_WEBP` | `95` | Default WebP web-export quality (1–100). |
| `KIM_WEB_QUALITY_AVIF` | `95` | Default AVIF web-export quality (1–100). |
| `KIM_COPYRIGHT_CREATOR` | Empty | Default creator/artist for copyright editing. |
| `KIM_COPYRIGHT_NOTICE` | Empty | Default copyright notice; supports `{YEAR}` replacement. |
| `KIM_COPYRIGHT_USAGE_RIGHTS` | Empty | Default usage-rights text. |

### Custom output filename labels

In **Settings → Output Filenames**, customize the descriptive labels KIM6 adds when it automatically names an output. Defaults are shown below. For example, the compression label can change from `compressed` to `com`, producing `photo_com.jpg` or `com_photo.jpg`, depending on prefix/suffix placement. The tab previews each filename and includes Restore Defaults.

| Operation | Configuration key | Default label |
|---|---|---|
| Compression | `KIM_AFFIX_COMPRESSED` | `compressed` |
| Resize | `KIM_AFFIX_RESIZED` | `resized` |
| Web export | `KIM_AFFIX_WEB` | `web` |
| Rotate | `KIM_AFFIX_ROTATED` | `rotated` |
| Auto-rotate | `KIM_AFFIX_AUTO_ROTATED` | `auto_rotated` |
| Flip horizontally | `KIM_AFFIX_FLIPPED_HORIZONTAL` | `flipped_horizontal` |
| Flip vertically | `KIM_AFFIX_FLIPPED_VERTICAL` | `flipped_vertical` |
| Remove all metadata | `KIM_AFFIX_STRIPPED` | `stripped` |
| Remove GPS metadata | `KIM_AFFIX_GPS` | `gps` |
| Remove AI metadata | `KIM_AFFIX_AI` | `ai` |
| Copyright information | `KIM_AFFIX_COPYRIGHT` | `copyright` |
| Shift capture time | `KIM_AFFIX_TIMESHIFT` | `timeshift` |
| Synchronize dates | `KIM_AFFIX_DATESYNC` | `datesync` |
| Video transcode | `KIM_AFFIX_TRANSCODED` | `transcoded` |
| Extract video frame | `KIM_AFFIX_FRAME` | `frame` |
| Video thumbnail | `KIM_AFFIX_THUMBNAIL` | `thumbnail` |
| Video contact sheet | `KIM_AFFIX_CONTACT_SHEET` | `contact-sheet` |
| Extract audio | `KIM_AFFIX_AUDIO` | `audio` |
| Remove video audio | `KIM_AFFIX_MUTED` | `muted` |
| GIF from video | `KIM_AFFIX_ANIMATED` | `animated` |
| Slideshow from photos | `KIM_AFFIX_SLIDESHOW` | `slideshow` |

Labels must contain 1–32 ASCII letters, digits, underscores or hyphens, beginning with a letter or digit. Invalid labels are rejected by the UI and ignored by the runtime. Existing collision numbering and protections against overwriting remain unchanged. Compound GPS/AI labels use both customized parts; video frame names keep their timestamp.

These options affect automatically named output files, not names explicitly chosen in a Save/Create dialog, ordinary format conversion, temporary files, or the Rename Images feature. Existing filename separators remain unchanged, including `clip-transcoded.mp4` and `clip-audio.mp3`.

PNG export uses lossless compression, so no lossy PNG quality setting is provided. Empty copyright defaults do not request clearing existing fields.

### Validation and behavior

- **Output policy:** `create` uses separate copies wherever supported. `prompt` defaults to **Create new files (originals untouched)** and requires a second explicit confirmation before replacing originals. Derived-only actions preserve selected sources.
- **Filename affixes:** The Output Filenames tab controls descriptive labels and their position for automatically named image, metadata and video results. User-chosen filenames and Rename Images have their own rules. Collision numbering remains before the extension and never silently replaces an existing file.
- **Web quality:** The dialog accepts integers from 1 to 100. Saved invalid values are ignored and the respective default of 95 applies. Explicit command-line `--quality` is validated for its invocation.
- **Web format and color:** Unsupported values cause failure rather than silent format substitution. `keep` retains the original format when supported; `srgb` needs compatible ICC handling.
- **Copyright:** Empty input fields leave corresponding metadata unchanged. `{YEAR}` in a notice is resolved by the copyright action as documented under [copyright](#copyright).

### Advanced command-line overrides

These environment-only options are **not** stored by the Settings dialog:

| Setting / environment variable | Default | Behavior |
|---|---|---|
| `KIM_WEB_FORMAT` | `jpg` | Default web-export format if not specified: `jpg`, `jpeg`, `png`, `webp`, `avif`, or `keep` where supported. |
| `KIM_WEB_COLOR_MODE` | `srgb` | `srgb` converts supported profiles for web export; `preserve` retains a compatible embedded profile. |
| `KIM_WEB_QUALITY` | `95` | Fallback quality when no format-specific value applies; JPEG/WebP/AVIF presets use their separate quality settings. |

Explicit options, including `--quality`, `--format`, and `--color`, take precedence for that invocation. Environment overrides must be present in the running command's environment (or Dolphin's environment). `KIM_POLICY=prompt` does not itself permit overwriting: a second explicit confirmation is required.

### Example saved settings

The Settings dialog creates a file like this, shown with default and empty demonstration values:

~~~ini
# KIM6 user preferences
# Environment variables take precedence.
KIM_POLICY=prompt
KIM_NAME_AFFIX_POSITION=suffix
KIM_WEB_QUALITY_JPEG=95
KIM_WEB_QUALITY_WEBP=95
KIM_WEB_QUALITY_AVIF=95
KIM_COPYRIGHT_CREATOR=
KIM_COPYRIGHT_NOTICE=
KIM_COPYRIGHT_USAGE_RIGHTS=
~~~

For a temporary command-line filename-prefix override:

~~~sh
KIM_NAME_AFFIX_POSITION=prefix ./src/bin/kim_all resize --size 1600x1600 -- photo.jpg
~~~

See [Output and File Handling](#output-and-file-handling), [copyright](#copyright), and [webexport](#webexport) for action-specific details.

## Still-image actions

### `album`

```sh
kim_all album -- FILE...
kim_all album OUTPUT_DIRECTORY FILE...
```

Prompts for one of eight PDF album layouts and a PDF destination. The optional first argument chooses the initial output directory. Produces an ordered, validated multi-page A4 PDF (portrait or landscape according to the chosen preset). Existing targets require the configured create/overwrite choice.

### `animate`

```sh
kim_all animate [--delay CENTISECONDS] [--loop COUNT] [--output PATH] -- IMAGE...
```

Creates an animated GIF from still images and their frames, in selection order. Without explicit options it prompts for delay (default 100 centiseconds) and loop count (default 0, infinite). Delay and loop are integers from 0 through 65535. This is distinct from `videogif`, which samples a video segment.

### `collage`

```sh
kim_all collage [--size WxH] [--tile COLUMNSxROWS] [--overlap PERCENT] [--background COLOR] [--border PERCENT] [--rotation DEGREES] [--random-rotation DEGREES] [--seed INTEGER] [--shadow|--no-shadow] [--output FILE] -- IMAGE...
```

Builds a PNG collage. Without arguments, prompts for canvas/tile size, overlap and background, then asks for output. Overlap is 0–90%, border 0–50%, rotation −180° to 180°, random rotation 0–180°, and seed is a nonnegative integer of at most nine digits. The default tile dimensions are `5x4`, overlap 15%, background grey, border 2% of tile width, random rotation ±15°, and shadow on. Uses selected order and staged publication.

### `compress`

```sh
kim_all compress --quality 1..100 [--output-dir DIR] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] -- JPEG...
kim_all compress --custom -- JPEG...
```

Accepts JPEG image content only. Quality is a decimal integer 1–100. Custom mode asks for quality and may ask for progressive/baseline scan and Huffman-table optimization. Progressive is the established default; baseline explicitly selects sequential scans. Optimization is an encoding option; a smaller file is not guaranteed. Create mode uses the configured `_compressed` affix and collision numbering. Authorized overwrite replaces the selected JPEG only after validation.

### `contactsheet`

```sh
kim_all contactsheet [--paper letter|a4] [--orientation portrait|landscape] [--grid 3x4|4x5|5x7] [--labels both|number|filename|none] [--fit fit|fill] [--background white|black] [--dpi 150|300] [--title TEXT] [--output PATH] [--interactive] -- IMAGE...
```

Creates a validated multi-page PDF contact sheet from selected single-frame images. Defaults: US Letter, portrait, 4x5 grid, number-and-filename labels, fit without cropping, white background, and 300 DPI. Other options include A4, landscape, 3x4 or 5x7 grids, center cropping, alternative labels, black background, and 150 DPI. Interactive mode asks for the settings. KIM6 stages and validates the PDF before collision-safe creation or separately authorized replacement. The selected images are never overwritten.

### `convert`

```sh
kim_all convert --format FORMAT [--bmp5] [--jp2-mode lossless|lossy] [--jp2-quality 1..100] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] -- FILE...
kim_all convert --custom-format -- FILE...
```

Dedicated menu formats include JPEG, PNG, GIF, BMP5, TIFF, PDF, WebP, AVIF, HEIC/HEIF, JPEG XL and JPEG 2000. Output depends on the installed coder/delegate; missing encoders fail rather than changing format. APNG is supported in the dedicated FFmpeg-based conversion path when FFmpeg/ffprobe are available. Animated APNG files are deliberately refused by Resize and Web Export because some ImageMagick decoders expose only the first animation frame. Nonanimated PNG files remain supported; failed APNG operations leave the original unchanged. Animated sources are not silently flattened by a conversion that cannot preserve frames. `--bmp5` is valid only with BMP output. JP2 defaults to lossy; `--jp2-mode lossless` uses the installed JPEG 2000 delegate’s lossless rate setting. `--jp2-quality` is JPEG-2000-specific, not equivalent to JPEG quality. JPEG scan/optimization flags apply only to JPEG output. Create or overwrite follows the output policy; source bytes remain protected.

### `copyright`

```sh
kim_all copyright [--creator TEXT] [--notice TEXT] [--usage-rights TEXT] [--year YYYY] -- FILE...
kim_all copyright --interactive -- FILE...
```

Updates only supplied nonempty fields. With no values or with `--interactive`, shows a form. `{YEAR}` in a notice expands to the capture year when available, otherwise the current year; `--year` supplies a fixed year. Writes the defined EXIF/IPTC/XMP fields without recompressing pixels. No-op updates do not publish a copy.

### `datesync`

```sh
kim_all datesync --direction exif-to-file -- FILE...
kim_all datesync --direction file-to-exif [--fields capture|all] -- FILE...
kim_all datesync --interactive -- FILE...
```

`exif-to-file` sets filesystem modification time from `DateTimeOriginal`; camera times without a zone use system local time, not UTC. `file-to-exif` writes capture time from filesystem mtime; `capture` writes `DateTimeOriginal`, while `all` also writes `CreateDate` and `ModifyDate`. The dialog previews the first selected file and confirms direction. Writing EXIF dates preserves image pixels without recompression and retains filesystem modification time. Filesystem creation time is not changed.

### `flipflop`

```sh
kim_all flipflop flip -- FILE...
kim_all flipflop flop -- FILE...
```

`flip` mirrors vertically; `flop` mirrors horizontally. Create mode publishes transformed copies, leaving selected originals unchanged. Overwrite mode requires explicit two-stage confirmation before replacing the originals with validated output.

### `gallery`

```sh
kim_all gallery -- IMAGE...
```

Prompts for title, author, layout/columns, and an output location. Builds an HTML gallery with resized images and thumbnails from mixed source directories. The complete directory is staged and published as a new directory; occupied directories are not recursively overwritten. Opens the resulting `index.html` with `xdg-open` when available.

### `print`

```sh
kim_all print -- IMAGE...
kim_all print OUTPUT_DIRECTORY IMAGE...
```

Prompts for one of seven print layouts and an output PDF. Layouts specify paper orientation, physical print dimensions or thumbnail grid. The optional first argument chooses the initial destination directory. Result is validated as an ordered, multi-page PDF.

### `rename`

```sh
kim_all rename MODE [--output-dir DIR] -- FILE...
kim_all rename interactive -- FILE...
```

The following rename modes are available:

| Mode | Description |
|---|---|
| `lowercase` | Convert filenames to lowercase. |
| `uppercase` | Convert filenames to uppercase. |
| `spacestodash` | Replace spaces with dashes. |
| `dashestospace` | Replace dashes with spaces. |
| `addprefix` | Add text to the beginning of filenames. |
| `addsuffix` | Add text to the end of filenames. |
| `overwrite` | Replace specified text within filenames, not overwrite image contents. |
| `exifdate` | Rename images using their EXIF capture dates. |
| `sequential` | Rename files using a numbered sequence. |
| `interactive` | Display a dialog to choose a rename operation. |

EXIF-date formats include `YYYYMMDD_HHMMSS`, `YYYY-MM-DD_HH-MM-SS`, `YYYY-DD-MM_HH-MM-SS`, and `IMG-YYYYMMDD_HHMMSS`.

Sequential mode prompts for a base name, starting number, and minimum number width (1–18). Supported modes allow a separate output directory.

KIM6 checks the complete batch for naming conflicts before making changes. Occupied paths are not overwritten. Cross-device moves copy and validate the bytes and metadata before publishing without clobbering and removing the unchanged source.

### `resize`

```sh
kim_all resize --size GEOMETRY [--output-dir DIR] -- IMAGE...
kim_all resize --percent PERCENT [--output-dir DIR] -- IMAGE...
kim_all resize --custom -- IMAGE...
kim_all resize --custom-percent -- IMAGE...
```

Geometry uses ImageMagick’s supported resize grammar and preserves aspect ratio for the menu presets. Percentage is an integer 1–1000; 100% keeps dimensions, values above 100% explicitly enlarge. ImageMagick rounding is used, with dimensions clamped to at least one pixel. Existing presets are maximum width/height bounds, not forced exact dimensions. Create mode uses `_resized`; authorized overwrite replaces only after validation. Animated APNG input is refused without changing the original, rather than risking silent frame loss; ordinary PNG is supported.

### `resizeandsend`

```sh
kim_all resizeandsend [--size full|WIDTHxHEIGHT] -- IMAGE...
```

Without `--size`, prompts for full size, 1600/1200/800/600/300 square bounds, or custom geometry. Only successfully prepared files are attached. Animated APNG cannot be resized for email because animation frames may be lost; `--size full` preserves the original animation by copying its bytes. KMail, Thunderbird, or `xdg-email` is used if available. Attachments are retained in `${XDG_DATA_HOME:-$HOME/.local/share}/kim6/email-attachments` because clients may read asynchronously; see [File handling](#output-and-file-handling).

KIM6 does not automatically delete prepared attachments. Remove them from the attachment directory when they are no longer needed. If no compatible mail program is available, KIM6 reports the directory so the files can be attached manually.

### `rotate`

```sh
kim_all rotate --angle DEGREES -- IMAGE...
kim_all rotate --exif -- IMAGE...
kim_all rotate --custom -- IMAGE...
```

Rotates by a supported signed decimal angle, auto-orients using EXIF, or prompts for a custom angle. Create mode publishes transformed copies. Overwrite mode replaces selected originals only after two-stage confirmation and output validation. Rotation preserves modification timestamps, including nanoseconds where supported, and validates image profiles and frame content.

### `rotatewithexif`

```sh
kim_all rotatewithexif IMAGE...
```

Retained dispatcher alias for EXIF-based orientation. The Dolphin menu uses `rotate --exif`.

### `stripmeta`

```sh
kim_all stripmeta [--mode all|gps|ai] [--remove-ai] [--interactive] -- IMAGE...
```

Default mode `all` preserves the existing full-strip behavior. `gps` removes recognized coordinate fields; `ai` removes recognized AI-generation fields, including IPTC AI prompts, prompt-writer name, AI system and AI system version. The DigitalSourceType field is removed only when it contains a recognized AI classification, not an unrelated classification. `--remove-ai` combines recognized AI-field removal with `all` or `gps`. Interactive mode selects a mode. GPS removal targets recognized coordinate fields; other metadata and visible scene details may still reveal a location. AI removal targets recognized AI-generation metadata, not every possible generator indicator. Unrecognized generator-specific fields and signed C2PA / Content Credentials may remain. ExifTool cannot guarantee their complete removal.

### `tiffjoin`

```sh
kim_all tiffjoin [--output PATH] [--] IMAGE...
```

Joins selected images/frames in selection order into a multi-page TIFF. Prompts for output and create/overwrite policy when not supplied/forced. Sources are preserved; output is staged and validated.

### `timeshift`

```sh
kim_all timeshift --offset [+|-]HH:MM:SS [--fields all|capture] -- IMAGE...
kim_all timeshift --interactive -- IMAGE...
```

Adds or subtracts the fixed offset from camera date tags. `all` (default) shifts `DateTimeOriginal`, `CreateDate`, and `ModifyDate`; `capture` shifts only `DateTimeOriginal`. Subsecond and timezone-offset tags remain unchanged, as do GPS timestamps and filesystem modification time. This shifts a camera’s wall-clock values; it does not convert time zones or reinterpret local time as UTC.

### `webexport`

```sh
kim_all webexport [--size WIDTHxHEIGHT] [--quality 1..100] [--format jpg|jpeg|png|webp|avif|keep] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] [--color srgb|preserve] [--output-dir DIR] -- IMAGE...
```

Options can also be prompted. Web Export accepts an output directory and selected source files. Default size is 1600×1600, default quality is 95 for JPEG, WebP and AVIF (independently configurable in Settings), format defaults to `KIM_WEB_FORMAT` (normally JPEG), and color defaults to ICC-managed sRGB. `keep` retains source format when supported. Web Export creates distinct derivatives. Animated APNG input is refused rather than flattened. JPEG scan and optimization options apply only to JPEG output.

With `--color srgb` (the default), tagged images undergo ICC conversion to sRGB. Untagged RGB images are treated as sRGB, while ambiguous untagged CMYK images are rejected. Color-managed conversion requires an installed sRGB profile and the appropriate source profile. `--color preserve` retains embedded color profiles where supported.

## Video actions

### `slideshow`

```sh
kim_all slideshow [--seconds-per-photo 1..30] [--size WxH] [--fps 1..30] [--background COLOR] [--output FILE] [--interactive] -- PHOTO...
```

Creates a derived, silent H.264/yuv420p MP4. Photos are sorted in natural filename order, fitted without upscaling, and padded. Defaults are 3 seconds per photo, 1280×720, 25 fps, black background. Interactive size choices are 1280×720, 1920×1080, and 854×480. Limits: 200 photos, 600 seconds total, 18,000 frames and 1920×1080. RAW, layered, vector, HDR, and animated sources are rejected. H.264 encoder `libx264` is required.

Slideshows do not include titles, transitions, pan, or zoom effects. They are intended for straightforward photo-to-video conversion, not video editing.

### `video`

```sh
kim_all video --size hd720|hd1080 --crf 17|23|29 --codec libx264|libx265 --container orig|mp4 -- VIDEO...
kim_all video --size hd720|hd1080 --codec av1 --av1-quality high|balanced|smallest|custom --container orig|mp4 -- VIDEO...
```

Dolphin exposes six MP4 presets for each of H.264 and H.265 (720p/1080p with three quality choices). Original-container output remains available through the CLI. For AV1 encoding, KIM6 uses `libsvtav1` when available or `libaom-av1` otherwise. If neither encoder is available, the operation fails rather than substituting H.264 or H.265. AV1 High uses CRF 28, Balanced CRF 35, Smallest File CRF 42, with encoder-specific speed settings; those values are not comparable to the H.264/H.265 CRFs. `custom` prompts for AV1 quality and speed through the CLI; the Dolphin AV1 menu offers six MP4 presets. Original-container mode fails when codecs/streams are incompatible instead of forcing MP4. Aspect ratio and orientation are handled; no unnecessary upscaling.

### `videoaudio`

```sh
kim_all videoaudio --mode extract --format m4a|mp3|flac|wav -- VIDEO...
kim_all videoaudio --mode mute -- VIDEO...
```

Extracts the first audio stream to the selected container; additional audio streams are not silently claimed as exported. Compatible AAC can be stream-copied to M4A. Mute creates a separate video file without audio tracks. The video stream is copied without re-encoding, preserving its original quality. If the source video has no audio, no new file is created.

### `videoframes`

```sh
kim_all videoframes --mode single --at HH:MM:SS[.sss] [--format png|jpg] -- VIDEO...
kim_all videoframes --mode thumbnail [--format png|jpg] -- VIDEO...
kim_all videoframes --mode contact [--grid 3x3|4x4|5x5] [--format png|jpg] -- VIDEO...
```

Extracts one frame, a representative midpoint thumbnail (not frame zero), or one labeled contact sheet. Contact sheets use 320×180 fit/pad tiles, sample evenly over duration, and may repeat positions for short videos. Display rotation is applied. The video contact sheet menu action opens one Qt dialog for grid and image format; single-frame extraction uses a timestamp prompt.

### `videogif`

```sh
kim_all videogif --start HH:MM:SS[.sss] --duration SECONDS --fps 10|12|15|24 --width 320|480|640|800 --loop infinite|once -- VIDEO...
```

Creates a palette-optimized GIF for the requested interval. Duration is greater than zero and at most 15 seconds, with at most 360 nominal frames and a 200-million output pixel-frame work bound. Width is a maximum and does not upscale; height follows aspect ratio. At least two output frames are required. Infinite uses GIF loop extension 0; once omits looping.

## Information actions

### `about`

```sh
kim_all about
```

Shows the installed About text in KDialog.

### `license`

```sh
kim_all license
```

Opens the installed `LICENSE.md` using `xdg-open`.

### `manual`

```sh
kim_all manual
```

Opens the installed KIM6 User Guide using `xdg-open`.

### `settings`

```sh
kim_all settings
```

Opens the graphical KIM6 settings dialog. No selected files are required.

## Troubleshooting

If an action fails, check the final KDialog report. Confirm that the source is readable, the destination is writable, and the required ImageMagick coder, FFmpeg encoder, or other dependency is installed.

When running `kim_all` directly, inspect the terminal output for diagnostics. Previously completed outputs remain available if a later batch item fails.

Test uncertain operations using disposable copies and `KIM_POLICY=create`, not important originals. See [FORMATS.md](FORMATS.md) for codec support and [INSTALL.md](../INSTALL.md) for missing Dolphin menus or installation problems.
