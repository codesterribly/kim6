
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
- [Still-image actions](#still-image-actions): album, animate, compress, convert, copyright, datesync, flipflop, gallery, pelemele, print, rename, resize, resizeandsend, rotate, rotatewithexif, stripmeta, timeshift, tiffjoin, webexport
- [Video actions](#video-actions): slideshow, video, videoframes, videoaudio, videogif
- [Information actions](#information-actions): about, license, manual

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
- **In-place operation:** Modifies the selected file directly. Rotation and flipping use this behavior.

Some metadata and timestamp operations have additional rules. Each command section describes its applicable behavior.

See [SAFETY.md](SAFETY.md) for file preservation and overwrite protections. The next section explains how to configure output policies and other defaults.

## Configuration and Defaults

KIM6 reads optional defaults from a KConfig file and environment variables. When an action accepts an explicit command-line option, that option takes precedence for the invocation. Otherwise, an environment variable takes precedence over the corresponding KConfig key, followed by the built-in default.

The default configuration file is `${XDG_CONFIG_HOME:-$HOME/.config}/kim_kdeimagemenu`. Set `KIM_CONFIG_FILE` to use a different file. The KConfig group is literally named `<default>`. The dispatcher reads supported KConfig values when it starts, so changes to the file apply to subsequent invocations. If the file is unavailable or unreadable, the dispatcher uses environment values and action defaults.

### Settings

| Environment variable | KConfig key | Default | Accepted values and purpose |
|---|---|---|---|
| `KIM_CONFIG_FILE` | — | `${XDG_CONFIG_HOME:-$HOME/.config}/kim_kdeimagemenu` | Path to the KConfig file; environment-only setting. |
| `KIM_POLICY` | `KIM_POLICY` | Prompt | `create` or `overwrite` for actions offering a file-handling choice. |
| `KIM_NAME_AFFIX_POSITION` | `NAME_AFFIX_POSITION` | `suffix` | `prefix` or `suffix` for generated filename tags. |
| `KIM_WEB_QUALITY` | `WEB_EXPORT_QUALITY` | `75` | Integer 1–100 for web export quality. |
| `KIM_WEB_FORMAT` | `WEB_EXPORT_FORMAT` | `jpg` | `jpg`, `jpeg`, `webp`, `avif`, or `keep` for web export. |
| `KIM_WEB_COLOR_MODE` | `WEB_COLOR_MODE` | `srgb` | `srgb` or `preserve` for web export color handling. |
| `KIM_COPYRIGHT_CREATOR` | `COPYRIGHT_CREATOR` | Empty | Default creator or artist text. |
| `KIM_COPYRIGHT_NOTICE` | `COPYRIGHT_NOTICE` | Empty | Default copyright notice; supports `{YEAR}`. |
| `KIM_COPYRIGHT_USAGE_RIGHTS` | `COPYRIGHT_USAGE_RIGHTS` | Empty | Default usage-rights text. |
| `KIM_GIF_DELAY` | — | `100` | Default animation delay in centiseconds (0–65535), used by the interactive `animate` dialog. |

`KIM_CONFIG_FILE` is an environment-only setting; it chooses the file containing the KConfig keys above. `KIM_GIF_DELAY` is also environment-only and is range-checked when the animation is requested. KIM6 uses `KIM_POLICY` alone for output policy; it does not support `KIM_MODE` as an alias.

### Validation and behavior

- **Output policy:** An unset or unsupported `KIM_POLICY` leaves the normal create/overwrite prompt available. `create` uses collision-safe output names; `overwrite` authorizes replacement only when the action supports it. Derived-only actions never replace selected originals merely because `KIM_POLICY=overwrite` is set.
- **Filename tags:** `prefix` places a generated tag before the complete filename stem; `suffix` places it after the stem. The extension stays at the end, and collision numbering remains before the extension. This setting applies to compression, resize, web export, and full metadata stripping, not to rename. Only the exact value `prefix` selects prefix mode; otherwise suffix behavior is used. KConfig accepts the two documented values.
- **Web quality:** Invalid KConfig values fall back to `75`. An invalid `KIM_WEB_QUALITY` environment value can appear as the dialog default but is rejected if submitted; an explicit `--quality` argument is validated for that invocation.
- **Web format and color:** Invalid KConfig entries fall back to `jpg` and `srgb`, respectively. Unsupported environment or command-line values cause the action to fail rather than silently choosing another format or color mode. `keep` retains the source format when supported.
- **Copyright fields:** Empty defaults mean no value is supplied. An empty field in the interactive dialog leaves that metadata field unchanged rather than clearing it. `{YEAR}` in a copyright notice is resolved as described under [`copyright`](#copyright).

### Example KConfig file

Create or edit `~/.config/kim_kdeimagemenu`:

```ini
[<default>]
KIM_POLICY=create
NAME_AFFIX_POSITION=suffix
WEB_EXPORT_QUALITY=75
WEB_EXPORT_FORMAT=jpg
WEB_COLOR_MODE=srgb
COPYRIGHT_CREATOR=Example Photographer
COPYRIGHT_NOTICE=Copyright © {YEAR} Example Photographer
COPYRIGHT_USAGE_RIGHTS=
```

Environment overrides must be present in the environment that launches Dolphin, or can be set for an individual terminal command. For example:

```sh
KIM_POLICY=create KIM_NAME_AFFIX_POSITION=prefix kim_all resize --size 1600x1600 -- photo.jpg
KIM_WEB_COLOR_MODE=preserve kim_all webexport --size 1600x1600 -- photo.jpg
```

When running from a source checkout, replace `kim_all` in those examples with `./src/bin/kim_all`. See [SAFETY.md](SAFETY.md) for action-specific metadata and timestamp rules.

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

### `compress`

```sh
kim_all compress --quality 1..100 [--output-dir DIR] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] -- JPEG...
kim_all compress --custom -- JPEG...
```

Accepts JPEG image content only. Quality is a decimal integer 1–100. Custom mode asks for quality and may ask for progressive/baseline scan and Huffman-table optimization. Progressive is the established default; baseline explicitly selects sequential scans. Optimization is an encoding option; a smaller file is not guaranteed. Create mode uses the configured `_compressed` affix and collision numbering. Authorized overwrite replaces the selected JPEG only after validation.

### `convert`

```sh
kim_all convert --format FORMAT [--bmp5] [--jp2-mode lossless|lossy] [--jp2-quality 1..100] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] -- FILE...
kim_all convert --custom-format -- FILE...
```

Dedicated menu formats include JPEG, PNG, GIF, BMP5, TIFF, PDF, WebP, AVIF, HEIC/HEIF, JPEG XL and JPEG 2000. Output depends on the installed coder/delegate; missing encoders fail rather than changing format. APNG is supported for animated PNG when FFmpeg/ffprobe are available. Animated sources are not silently flattened by a conversion that cannot preserve frames. `--bmp5` is valid only with BMP output. JP2 defaults to lossy; `--jp2-mode lossless` uses the installed JPEG 2000 delegate’s lossless rate setting. `--jp2-quality` is JPEG-2000-specific, not equivalent to JPEG quality. JPEG scan/optimization flags apply only to JPEG output. Create or overwrite follows the output policy; source bytes remain protected.

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

`flip` mirrors vertically; `flop` mirrors horizontally. These are explicitly in-place transformations, independent of `KIM_POLICY`; the staged result replaces the selected image only after validation.

### `gallery`

```sh
kim_all gallery -- IMAGE...
```

Prompts for title, author, layout/columns, and an output location. Builds an HTML gallery with resized images and thumbnails from mixed source directories. The complete directory is staged and published as a new directory; occupied directories are not recursively overwritten. Opens the resulting `index.html` with `xdg-open` when available.

### `pelemele`

```sh
kim_all pelemele [--size WxH] [--tile COLUMNSxROWS] [--overlap PERCENT] [--background COLOR] [--border PERCENT] [--rotation DEGREES] [--random-rotation DEGREES] [--seed INTEGER] [--shadow|--no-shadow] [--output FILE] -- IMAGE...
```

Builds a PNG collage. Without arguments, prompts for canvas/tile size, overlap and background, then asks for output. Overlap is 0–90%, border 0–50%, rotation −180° to 180°, random rotation 0–180°, and seed is a nonnegative integer of at most nine digits. The default tile dimensions are `5x4`, overlap 15%, background grey, border 2% of tile width, random rotation ±15°, and shadow on. Uses selected order and staged publication.

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

Geometry uses ImageMagick’s supported resize grammar and preserves aspect ratio for the menu presets. Percentage is an integer 1–1000; 100% keeps dimensions, values above 100% explicitly enlarge. ImageMagick rounding is used, with dimensions clamped to at least one pixel. Existing presets are maximum width/height bounds, not forced exact dimensions. Create mode uses `_resized`; authorized overwrite replaces only after validation.

### `resizeandsend`

```sh
kim_all resizeandsend [--size full|WIDTHxHEIGHT] -- IMAGE...
```

Without `--size`, prompts for full size, 1600/1200/800/600/300 square bounds, or custom geometry. Only successfully prepared files are attached. KMail, Thunderbird, or `xdg-email` is used if available. Attachments are retained in `${XDG_DATA_HOME:-$HOME/.local/share}/kim6/email-attachments` because clients may read asynchronously; see [SAFETY.md](SAFETY.md).

### `rotate`

```sh
kim_all rotate --angle DEGREES -- IMAGE...
kim_all rotate --exif -- IMAGE...
kim_all rotate --custom -- IMAGE...
```

Rotates by a supported signed decimal angle, auto-orients using EXIF, or prompts for a custom angle. This is an explicitly in-place transformation, independent of `KIM_POLICY`. It keeps image profiles and validated frame content; rotation preserves source mtime including nanoseconds where supported.

### `rotatewithexif`

```sh
kim_all rotatewithexif IMAGE...
```

Retained dispatcher alias for EXIF-based orientation. The Dolphin menu uses `rotate --exif`.

### `stripmeta`

```sh
kim_all stripmeta [--mode all|gps|ai] [--remove-ai] [--interactive] -- IMAGE...
```

Default mode `all` preserves the existing full-strip behavior. `gps` removes recognized coordinate fields; `ai` removes recognized AI-generation fields. `--remove-ai` combines recognized AI-field removal with `all` or `gps`. Interactive mode selects a mode. GPS removal is not a guarantee of complete location anonymization. ExifTool cannot guarantee removal of signed C2PA Content Credentials.

### `timeshift`

```sh
kim_all timeshift --offset [+|-]HH:MM:SS [--fields all|capture] -- IMAGE...
kim_all timeshift --interactive -- IMAGE...
```

Adds or subtracts the fixed offset from camera date tags. `all` (default) shifts `DateTimeOriginal`, `CreateDate`, and `ModifyDate`; `capture` shifts only `DateTimeOriginal`. Subsecond and timezone-offset tags remain unchanged, as do GPS timestamps and filesystem modification time. This shifts a camera’s wall-clock values; it does not convert time zones or reinterpret local time as UTC.

### `tiffjoin`

```sh
kim_all tiffjoin [--output PATH] [--] IMAGE...
```

Joins selected images/frames in selection order into a multi-page TIFF. Prompts for output and create/overwrite policy when not supplied/forced. Sources are preserved; output is staged and validated.

### `webexport`

```sh
kim_all webexport [--size WIDTHxHEIGHT] [--quality 1..100] [--format jpg|webp|avif|keep] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] [--color srgb|preserve] [--output-dir DIR] -- IMAGE...
```

Options can also be prompted. The legacy `webexport OUTPUT_DIRECTORY FILE...` dispatcher form remains accepted. Default size is 1600×1600, default quality is 75, format defaults to `KIM_WEB_FORMAT` (normally JPEG), and color defaults to ICC-managed sRGB. `keep` retains source format when supported. Web export always creates a distinct derivative, including under `KIM_POLICY=overwrite`. JPEG scan/optimization options apply only to JPEG output.

## Video actions

### `slideshow`

```sh
kim_all slideshow [--seconds-per-photo 1..30] [--size WxH] [--fps 1..30] [--background COLOR] [--output FILE] [--interactive] -- PHOTO...
```

Creates a derived, silent H.264/yuv420p MP4. Photos are sorted in natural filename order, fitted without upscaling, and padded. Defaults are 3 seconds per photo, 1280×720, 25 fps, black background. Interactive size choices are 1280×720, 1920×1080, and 854×480. Limits: 200 photos, 600 seconds total, 18,000 frames and 1920×1080. RAW, layered, vector, HDR, and animated sources are rejected. H.264 encoder `libx264` is required.

### `video`

```sh
kim_all video --size hd720|hd1080 --crf 17|23|29 --codec libx264|libx265 --container orig|mp4 -- VIDEO...
kim_all video --size hd720|hd1080 --codec av1 --av1-quality high|balanced|custom --container orig|mp4 -- VIDEO...
```

H.264/H.265 uses the existing 24 presets. For AV1 encoding, KIM6 uses `libsvtav1` when available or `libaom-av1` otherwise. If neither encoder is available, the operation fails rather than substituting H.264 or H.265. AV1 High uses CRF 28, Balanced CRF 35, with encoder-specific speed settings; those values are not comparable to the H.264/H.265 CRFs. `custom` prompts for AV1 quality and speed. Original-container mode fails when codecs/streams are incompatible instead of forcing MP4. Aspect ratio and orientation are handled; no unnecessary upscaling.

### `videoframes`

```sh
kim_all videoframes --mode single --at HH:MM:SS[.sss] [--format png|jpg] -- VIDEO...
kim_all videoframes --mode thumbnail [--format png|jpg] -- VIDEO...
kim_all videoframes --mode contact [--grid 3x3|4x4|5x5] [--format png|jpg] -- VIDEO...
```

Extracts one frame, a representative midpoint thumbnail (not frame zero), or one labeled contact sheet. Contact sheets use 320×180 fit/pad tiles, sample evenly over duration, and may repeat positions for short videos. Display rotation is applied. Interactive menu entries ask for needed options.

### `videoaudio`

```sh
kim_all videoaudio --mode extract --format m4a|mp3|flac|wav -- VIDEO...
kim_all videoaudio --mode mute -- VIDEO...
```

Extracts the first audio stream to the selected container; additional audio streams are not silently claimed as exported. Compatible AAC can be stream-copied to M4A. Mute creates a separate video file without audio tracks. The video stream is copied without re-encoding, preserving its original quality. If the source video has no audio, no new file is created.

### `videogif`

```sh
kim_all videogif --start HH:MM:SS[.sss] --duration SECONDS --fps 10|12|15|24 --width 320|480|640|800 --loop infinite|once -- VIDEO...
```

Creates a palette-optimized GIF for the requested interval. Duration is greater than zero and at most 60 seconds, with at most 1440 nominal frames and a 200-million output pixel-frame work bound. Width is a maximum and does not upscale; height follows aspect ratio. At least two output frames are required. Infinite uses GIF loop extension 0; once omits looping.

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

Opens the installed static manual using `xdg-open`.
