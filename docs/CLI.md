# `kim_all` command reference

The dispatcher is normally launched by Dolphin. In examples, `kim_all` means the installed `.../kim6/bin/kim_all` path, or `./src/bin/kim_all` from a checkout. Quote paths normally and pass selected files after `--` so option-looking filenames remain file arguments, except where an action documents a positional output-directory argument. Commands may prompt through KDialog unless their documented flags supply the setting. See [CONFIGURATION.md](CONFIGURATION.md) for output policy and defaults; see [ACTIONS.md](ACTIONS.md) for all 107 menu entries and their exact calls.

## Contents

- [Still-image actions](#still-image-actions): album, animate, compress, convert, copyright, datesync, flipflop, gallery, pelemele, print, rename, resize, resizeandsend, rotate, rotatewithexif, stripmeta, timeshift, tiffjoin, webexport
- [Video actions](#video-actions): slideshow, video, videoframes, videoaudio, videogif
- [Information actions](#information-actions): about, license, manual

```text
kim_all <command> [options] -- FILE...
```
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

`exif-to-file` sets filesystem modification time from `DateTimeOriginal`; camera times without a zone use system local time, not UTC. `file-to-exif` writes capture time from filesystem mtime; `capture` writes `DateTimeOriginal`, while `all` also writes `CreateDate` and `ModifyDate`. The dialog previews the first selected file and confirms direction. Metadata updates preserve image bytes and file mtime. Filesystem creation time is not changed.

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

Modes: `lowercase`, `uppercase`, `spacestodash`, `dashestospace`, `addprefix`, `addsuffix`, `overwrite` (literal text replacement), `exifdate`, `sequential`, and `interactive`. Interactive mode selects the operation and asks for needed values. EXIF-date formats are `YYYYMMDD_HHMMSS`, `YYYY-MM-DD_HH-MM-SS`, `YYYY-DD-MM_HH-MM-SS`, and `IMG-YYYYMMDD_HHMMSS`. Sequential mode prompts for base, start and minimum number width (1–18). An output directory can be chosen for supported modes. The complete batch is preflighted; occupied paths are never blindly overwritten. Cross-device moves copy, validate metadata/bytes, publish without clobbering, then remove the unchanged source.

### `resize`

```sh
kim_all resize --size GEOMETRY [--output-dir DIR] -- IMAGE...
kim_all resize --percent 1..1000 [--output-dir DIR] -- IMAGE...
kim_all resize --custom|--custom-percent -- IMAGE...
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

Adds or subtracts the fixed offset from camera date tags. `all` (default) shifts `DateTimeOriginal`, `CreateDate`, and `ModifyDate`; `capture` shifts only `DateTimeOriginal`. Subsecond and timezone-offset tags are handled for consistency. This shifts a camera’s wall-clock values; it does not convert time zones or reinterpret local time as UTC.

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

H.264/H.265 uses the existing 24 presets. AV1 prefers `libsvtav1`, falling back to `libaom-av1` only when SVT-AV1 is unavailable; it never falls back to H.264/H.265. AV1 High uses CRF 28, Balanced CRF 35, with encoder-specific speed settings; those values are not comparable to the H.264/H.265 CRFs. `custom` prompts for AV1 quality and speed. Original-container mode fails when codecs/streams are incompatible instead of forcing MP4. Aspect ratio and orientation are handled; no unnecessary upscaling.

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

Extracts the first audio stream to the selected container; additional audio streams are not silently claimed as exported. Compatible AAC can be stream-copied to M4A. Mute remuxes video without re-encoding and removes audio streams; already silent input is a no-op.

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
