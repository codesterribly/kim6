
# KIMng Command and Configuration Reference

`kim_all` is KIMng's main executable. Dolphin normally runs it through the service menus, but it can also be called directly from a terminal.

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
- [Recipes](#recipes)
- [Publishing your image gallery](#publishing-your-image-gallery)
- [Configuration and Defaults](#configuration-and-defaults)
- [Still-image actions](#still-image-actions): album, animate, capturedate, checkextensions, collage, compress, contactsheet, convert, copyright, datesync, flipflop, gallery-choose, gallery, photo-story, location-gpx, location-copy, location-apply, location-report, location-reduce, metadata-view, metadata-edit, pdf-pages, pdf-extract, print, rename, resize, resizeandsend, rotate, rotatewithexif, stripmeta, tiffjoin, timeshift, webexport, crop, overlay
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

KIMng uses different file-handling rules depending on the operation.

- **Create new:** Generates a separate file, normally using an action-specific filename suffix. Existing filenames are handled without silently replacing them.
- **Overwrite:** Replaces an existing file only when the operation supports it and replacement is authorized.
- **Derived output:** Always creates a separate result, regardless of `KIM_POLICY`.
- **In-place operation:** Replaces a selected original after explicit authorization, but only when the action supports replacement. Rotation can offer this option. Horizontal and vertical Flip do not: they always create reviewed copies.

The output-policy prompt defaults to **Create new files (originals untouched)**. Selecting **Overwrite originals (confirmation required)** requires a second, action-specific warning identifying the selected-file count. Canceling either dialog or losing access to KDialog refuses replacement. Authorization applies to the selected batch.

Some metadata and timestamp operations have additional rules. Each command section describes its applicable behavior.

**Interactive Review Changes policies:** Compress, Resize, and Convert video can show their own Create/Overwrite controls, initially selecting Create. Their available choices are not necessarily restricted by `KIM_POLICY`. Interactive Rename has its own copy-versus-rename controls. Conversion with `--preview`, interactive metadata stripping and copyright actions, and horizontal or vertical Flip have create-only reviewed workflows. Web Export, PDF page conversion, PDF embedded-image extraction, and Photo story publication also create separate outputs. Do not interpret `KIM_POLICY=create` as a universal prohibition enforced by every interactive dialog; inspect that operation's controls and approved review plan. No saved preference alone authorizes original-file replacement.

See [File preservation details](#file-preservation-details) below for operation-specific preservation and overwrite protections.

### File preservation details

Compression, conversion, resizing, and metadata changes support Create or explicitly authorized Overwrite behavior according to the action. Rotation and EXIF auto-orientation can publish separate copies or replace originals after confirmation where supported. Flipping and flopping always publish separate reviewed copies and never replace selected originals. Rename preflights conflicts before moving or copying files. Exports, email preparations, extracted video media, slideshows, galleries, and other derived publications preserve selected sources. Video transcoding can replace a selected original after explicit confirmation.

Metadata-only edits do not recompress image pixels. Rotation preserves source modification time, while flipping gives the changed file a fresh modification time. EXIF-to-filesystem date synchronization deliberately changes filesystem modification time; file-to-EXIF synchronization edits embedded timestamps instead. There is no global promise to preserve every metadata field or filesystem timestamp.

Existing destinations are protected by staged validation and publication checks. For symlink, hardlink, cancellation, atomic-replacement and race-condition limitations, see [File publication and cancellation](DEVELOPMENT.md#file-publication-and-cancellation).

For compression, conversion, resizing, metadata stripping and copyright editing, duplicate file identities (including aliases to the same file) cause the entire selection to be rejected before processing. Rotation and flipping instead report a repeated source as a failed item without transforming it again; camera-time shifting skips repeated paths and canonical-parent aliases after a successful update. All these actions reject filenames containing line breaks before processing. A processing failure returns a nonzero exit status even when other files in that batch were completed successfully; already published outputs are retained.

## Configuration and Defaults

**For normal use, open Settings in Dolphin:** Right-click a supported file and choose **Actions → KIMng - Settings/About → Settings**. Choose whether actions prompt about replacement or automatically create separate copies where supported. The **Output Filenames** tab lets you customize the labels automatically added to output names, choose prefix or suffix placement, and preview examples. You can also set separate JPEG/WebP/AVIF web-export quality defaults and copyright details. Click **Save**. KIMng reads these settings for subsequent actions; no manual configuration editing or Dolphin restart is required.

### Settings

The graphical Settings dialog writes `${XDG_CONFIG_HOME:-$HOME/.config}/kimng/settings.conf` (normally `~/.config/kimng/settings.conf`). It is a simple validated `KEY=value` text file, **not** KConfig and not an executable shell script. The dispatcher reads supported keys at startup. Explicit environment variables override their corresponding saved values, but cannot authorize overwriting without confirmation.

| Setting / environment variable | Default | Behavior |
|---|---|---|
| `KIM_POLICY` | `prompt` | The legacy output-policy mechanism uses `prompt` to request a Create/Overwrite choice where supported, or `create` to select separate outputs. Some Qt Review Changes dialogs manage their own Create/Overwrite controls rather than restricting available choices based on this setting. No setting silently authorizes replacement. |
| `KIM_NAME_AFFIX_POSITION` | `suffix` | Generated name tags appear after (`photo_web.jpg`) or before (`web_photo.jpg`) the filename stem. |
| `KIM_AFFIX_*` | See below | User-configurable labels for automatically generated output filenames. |
| `KIM_WEB_QUALITY_JPEG` | `95` | Default JPEG web-export quality (1–100). |
| `KIM_WEB_QUALITY_WEBP` | `95` | Default WebP web-export quality (1–100). |
| `KIM_WEB_QUALITY_AVIF` | `95` | Default AVIF web-export quality (1–100). |
| `KIM_COPYRIGHT_CREATOR` | Empty | Default creator/artist for copyright editing. |
| `KIM_COPYRIGHT_NOTICE` | Empty | Default copyright notice; supports `{YEAR}` replacement. |
| `KIM_COPYRIGHT_USAGE_RIGHTS` | Empty | Default usage-rights text. |

**Location settings:** The Settings dialog also saves `KIM_LOCATION_UNITS` (default `system`, with Imperial and Metric choices) and `KIM_LOCATION_ONLINE_MAPS` (default `no`, allow online map loading when enabled). These are normal Settings choices; do not assume they can be overridden by manually setting shell environment variables.

**Metadata settings:** The Settings dialog also has a Metadata tab for metadata-source priority and display preferences. These Qt-specific preferences use `QSettings("KIMng", "MetadataTools")`, separate from the dispatcher's `settings.conf` file. Do not treat these preferences as shell environment overrides.

### Custom output filename labels

In **Settings → Output Filenames**, customize the descriptive labels KIMng adds when it automatically names an output. Defaults are shown below. For example, the compression label can change from `compressed` to `com`, producing `photo_com.jpg` or `com_photo.jpg`, depending on prefix/suffix placement. The tab previews each filename and includes Restore Defaults.

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

These options affect automatically named output files, not names explicitly chosen in a Save/Create dialog, ordinary format conversion, temporary files, or the Rename Images feature. Some date/location outputs use fixed `_dated` and `_location` labels rather than these customizable affixes. Existing filename separators remain unchanged, including `clip-transcoded.mp4` and `clip-audio.mp3`.

PNG export uses lossless compression, so no lossy PNG quality setting is provided. Empty copyright defaults do not request clearing existing fields.

### Validation and behavior

- **Output policy:** The legacy policy mechanism uses `create` for separate copies where supported, while `prompt` offers a Create/Overwrite choice when the action supports replacement. Interactive Qt Review Changes dialogs may provide their own policy controls instead. Replacement always requires explicit approval and applicable safety checks. Create-only operations preserve selected sources regardless of the configured policy.
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
# KIMng user preferences
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

See [copyright](#copyright), [webexport](#webexport), and the earlier [file-preservation rules](#output-and-file-handling) for action-specific behavior.

## Recipes

The **KIMng - Recipes** submenu in Dolphin provides **Run a recipe…** and **Recipe editor…**. Open **Run a recipe…** to select one of the **eight built-in Recipes** grouped under **Common** (**Web Export**, **Share Privately**), **Adventure** (**Protect Sensitive Locations**), and **Asset Management** (**Create Client Proofs**, **Prepare Client Delivery**, **Prepare Editorial Submission**, **Organize by Capture Date**, **Apply Photographer Attribution**), or browse saved user Recipes under **Root**, named folders, and **Unfiled**. User Recipes explicitly assigned to **Root** also appear as direct shortcuts in Dolphin; other folders appear in the selector rather than as nested Dolphin menus. See [ACTIONS.md](ACTIONS.md) for the two static service-menu entry points.

Recipes use versioned JSON definitions: **schema 3** for fixed Recipes and **schema 4** for Recipes with run-time parameters, conditional operations (`enabled_when`), visibility conditions (`visible_when`), **Advanced settings**, and remembered answers. All 30 registered operations cover Geometry & Orientation, Format & Color, Metadata & Copyright (including **Reduce GPS Precision**, **Set Caption / Description**, and **Set Keywords**), and Filenames & Dates.

Recipes are derivative-only: originals are never replaced, and both source images and watermark assets are read through protected `O_NOATIME` descriptors. Output patterns support `{filename}` (plus legacy `{stem}`), `{date}`, `{index}`, and Recipe questions; nested relative subfolders up to 8 levels deep support optional `{param:...}` segments and per-image capture-date tokens (`{year}`, `{capture_date}`). Duplicate output targets within a batch are blocked during **Review Changes** before execution, and late collisions or post-approval source/asset changes fail closed without overwriting or silently renumbering.

PSD sources are readable in supported workflows, but KIMng cannot publish PSD output. A missing required format causes a preflight problem and can be corrected through **Fix recipe…** by adding **Convert Format** and choosing an available output type. KIMng does not silently choose a fallback encoder.

For all eight built-in Recipes, practical workflows, all 30 operations, folder organization, and safety rules, see the [Recipes reference](RECIPES.md).

### `recipe`

```sh
kim_all recipe --list
kim_all recipe --editor [-- FILE...]
kim_all recipe --choose [-- FILE...]
kim_all recipe --run-id ID [-- FILE...]
kim_all recipe --recipe ID_OR_JSON_FILE [--preview] [--destination DIR] -- FILE...
kim_all recipe --sync-menu
```

`--list` prints built-in and saved user Recipe definitions as JSON. `--editor` opens Recipe Editor; omitting `--recipe` also opens the editor. `--choose` opens Run a Recipe with no Recipe selected. `--run-id` opens the Runner for a saved Recipe ID without executing automatically. These graphical forms accept an optional initial file selection.

`--recipe` selects a fixed (schema 3) built-in or saved user Recipe by ID, or reads one from a JSON file, and requires at least one input file. Parameterized (schema 4) Recipes that ask questions require the interactive GUI Runner (`--run-id` or `--choose`) and are rejected in noninteractive `--recipe` CLI mode. `--preview` prints planned outputs and problems as JSON without publishing files. `--destination` supplies or overrides the directory for a Recipe with a directory destination; beside-source and subfolder destinations use the Recipe definition. Preflight problems or execution failures return a nonzero status. `--sync-menu` rebuilds installed Root shortcuts from the saved library. `--help` shows the accepted arguments. Recipes always create derivatives; CLI execution binds one complete plan before publication and blocks occupied or duplicate targets without numbering.

## Still-image actions

### `album`

```sh
kim_all album -- FILE...
kim_all album OUTPUT_DIRECTORY FILE...
```

Prompts for one of eight PDF album layouts and a PDF destination. The legacy positional output-directory argument is accepted but is not used to select the destination. Choose the output PDF in the Qt Album dialog, which also supports image ordering and caption sources (filename, capture date, camera details, embedded captions, or per-image custom captions). Produces an ordered, validated multi-page A4 PDF (portrait or landscape according to the chosen preset). Albums always create new files, regardless of `KIM_POLICY`; occupied names are numbered without replacing existing targets.

### `animate`

```sh
kim_all animate [--format gif|apng] [--delay CENTISECONDS] [--loop COUNT] [--canvas-mode fit|fill|preserve] [--output PATH] -- IMAGE...
```

Creates animated image derivatives using the supported settings and backend for the selected format. GIF and APNG arguments describe the available backend implementations, not a guarantee that every format is enabled in the graphical workflow. The interactive action provides settings for frame delay, looping and destination. GIF retains its ImageMagick path and supports 0–65535-centisecond delays, including multi-frame inputs. APNG uses FFmpeg and requires 2–360 single-frame sources, delay 1–65535 centiseconds, a transparent normalized RGBA canvas up to 4096 × 4096 and a total budget of 200 million pixel-frames. APNG uses a `.png` filename and verifies frame count, dimensions, timing, looping and decoding before publication. Canvas handling can be selected using `--canvas-mode fit|fill|preserve`, subject to the selected format's restrictions. The originals are never replaced. This is distinct from `videogif`, which samples video.

### `capturedate`

```sh
kim_all capturedate --mode unified --interactive -- FILE...
kim_all capturedate --interactive -- FILE...
kim_all capturedate --datetime 'YYYY-MM-DD HH:MM:SS' --timezone unknown|UTC|+HH:MM -- FILE...
kim_all capturedate --mode exif-to-file|file-to-exif|shift [--timezone UTC|+HH:MM] [--seconds INTEGER] [--fields capture|all] -- FILE...
```

The Dolphin **Set dates…** action edits camera capture-date metadata. `capturedate --mode unified` opens the unified photo-date workflow. The related photo-date actions
can adjust an existing capture date, derive a capture date from the file modification time, or synchronize
the file modification time with the recorded photo capture date. Unknown camera time zones are not assumed
to be UTC or the computer local time.

See also [`datesync`](#datesync) and [`timeshift`](#timeshift).
### `checkextensions`

    kim_all checkextensions -- FILE...

Checks selected image filenames against their detected file formats.
The Dolphin action is **Check and correct extensions…**.
It provides a review before creating correctly named copies; the selected originals are preserved.


The `--directory DIR` option selects a directory for extension checking. For example:

~~~sh
kim_all checkextensions --directory DIR
~~~
### `collage`

```sh
kim_all collage [--size WxH] [--tile COLUMNSxROWS] [--overlap PERCENT] [--background COLOR] [--border PERCENT] [--rotation DEGREES] [--random-rotation DEGREES] [--seed INTEGER] [--shadow|--no-shadow] [--layout LAYOUT] [--canvas CANVAS] [--fit FIT] [--gap GAP] [--frame FRAME] [--shuffle] [--output FILE] -- IMAGE...
```

Builds a PNG collage. Without explicit rendering options, the Dolphin action opens one Qt dialog for image ordering, layout, canvas, fit, gaps, frames, background, and an approximate composition preview before selecting output. Overlap is 0–90%, border 0–50%, rotation −180° to 180°, random rotation 0–180°, and seed is a nonnegative integer of at most nine digits. The default tile dimensions are `5x4`, overlap 15%, background grey, border 2% of tile width, random rotation ±15°, and shadow on. Uses selected order and staged publication.

### `crop`

~~~sh
kim_all crop -- IMAGE...
~~~

Opens the standalone interactive **Crop** workflow for selected images.

Choose the crop area using the image preview, aspect-ratio controls, exact pixel dimensions, or manual selection. Inspect the proposed results in **Review Changes** before applying them.

The review identifies source images, planned output names, destinations, and blocked items. Existing output-name conflicts are resolved during planning where supported; an output that becomes occupied after approval must not silently replace a file or be renamed without renewed review.

This is the standalone Crop action, not the Crop Image operation inside a saved Recipe.

### `overlay`

~~~sh
kim_all overlay -- IMAGE...
~~~

Opens the interactive **Add watermark…** workflow for selected images.

The dialog provides four types of image overlays:

- **Text watermark:** Add text to the image.
- **Image watermark/logo:** Apply a selected image as a watermark or logo.
- **Camera & EXIF details:** Render selected camera or EXIF information onto the image.
- **Caption overlay:** Add a caption to the image.

Overlay operations produce rendered image results rather than merely adding metadata fields. Inspect the settings and planned output before applying changes. Use the workflow's review and output controls to determine filenames and destinations.

### `compress`

~~~sh
kim_all compress --recommended [--interactive] -- IMAGE...
kim_all compress --maximum [--interactive] -- IMAGE...
kim_all compress --custom -- IMAGE...
kim_all compress --quality 1..100 [--output-dir DIR] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] -- IMAGE...
~~~

Compresses supported JPEG, PNG, WebP, and AVIF images. Available encoding options depend on the image format and installed encoders.

The Dolphin compression menu provides three choices:

- **Recommended:** Quality 85 for supported lossy formats; PNG compression level 6.
- **Maximum:** Quality 70 for supported lossy formats; PNG compression level 9.
- **Custom:** Opens format-specific compression settings.

JPEG, WebP, and AVIF quality settings control lossy encoding. PNG compression levels range from 0 to 9 and remain lossless. A higher PNG level may take longer but does not reduce image quality.

JPEG-specific controls include progressive or baseline scans and optional Huffman-table optimization. These do not apply to other formats. A smaller output file is not guaranteed.

The interactive workflow provides compression settings and a mandatory Review Changes step showing planned results and destinations.

Create mode publishes separate images with the configured compression filename label. When the dialog supports authorized replacement, overwriting requires explicit approval. Existing destinations and late collisions cannot silently replace files or change approved output filenames.

### `contactsheet`

```sh
kim_all contactsheet [--paper letter|a4] [--orientation portrait|landscape] [--grid auto|3x4|4x5|5x7] [--labels both|number|filename|none|capture|camera|embedded] [--fit fit|fill] [--background white|black] [--dpi 150|300] [--title TEXT] [--font-size auto|small|medium|large] [--label-placement below|above] [--output PATH] [--interactive] -- IMAGE...
```

Creates a validated multi-page PDF contact sheet from selected single-frame images. Defaults: US Letter, portrait, automatic grid selection, number-and-filename labels, fit without cropping, white background, and 300 DPI. Other options include A4, landscape, 3x4 or 5x7 grids, center cropping, alternative labels, black background, and 150 DPI. Interactive mode opens the Qt contact-sheet settings dialog. The layout can also use capture-date, camera, or embedded-caption labels, adjustable font sizes, and label placement above or below the images. KIMng stages and validates the PDF before create-only publication. Existing target files are not overwritten, and the selected images are never changed.

### `convert`

```sh
kim_all convert --format FORMAT [--preview] [--output-dir DIR] [--bmp5] [--jp2-mode lossless|lossy] [--jp2-quality 1..100] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] -- FILE...
kim_all convert --format pdf --strip-metadata -- DOCUMENT.psd
kim_all convert --preview --custom-format -- FILE...
```

Dedicated menu formats include JPEG, PNG, GIF, BMP5, TIFF, PDF, WebP, AVIF, HEIC/HEIF, JPEG XL and JPEG 2000. Output depends on the installed coder/delegate; missing encoders fail rather than changing format. APNG has a dedicated FFmpeg-based conversion path with operation-specific capability and validation requirements. The existence of this backend does not guarantee that APNG is available in the interactive format selector. Animated APNG files are deliberately refused by Resize and Web Export because some ImageMagick decoders expose only the first animation frame. Nonanimated PNG files remain supported; failed APNG operations leave the original unchanged. Animated sources are not silently flattened by a conversion that cannot preserve frames. `--bmp5` is valid only with BMP output. JP2 defaults to lossy; `--jp2-mode lossless` uses the installed JPEG 2000 delegate’s lossless rate setting. `--jp2-quality` is JPEG-2000-specific, not equivalent to JPEG quality. JPEG scan/optimization flags apply only to JPEG output. Create or overwrite follows the output policy; source bytes remain protected.

The `--preview` option opens the interactive conversion workflow, including settings and review of the planned results before publication. Dolphin's dedicated conversion actions and **Convert custom…** use this option. The `--output-dir DIR` option specifies a destination directory for supported command-line conversion. The `--strip-metadata` option is restricted to **PSD-to-PDF conversion**. It is rejected for other output formats or non-PSD inputs. For general metadata removal, use `stripmeta` or the corresponding Dolphin metadata actions. This option does not bypass output validation.

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

`exif-to-file` sets filesystem modification time from `DateTimeOriginal` only when a valid time and explicit timezone can be established; unknown camera timezones are not silently interpreted as the computer's local time or UTC. `file-to-exif` writes capture time from filesystem mtime using an established camera timezone. An unknown camera timezone blocks the operation; `capture` writes `DateTimeOriginal`, while `all` also writes `CreateDate` and `ModifyDate`. The interactive command delegates to the unified Qt photo-date workflow rather than using the legacy direction prompt; it reviews planned changes before execution. Writing EXIF dates preserves image pixels without recompression and retains filesystem modification time. Filesystem creation time is not changed.

### `flipflop`

```sh
kim_all flipflop flip -- FILE...
kim_all flipflop flop -- FILE...
```

`flip` mirrors vertically; `flop` mirrors horizontally. Both operations are strictly create-only. They open Review Changes to show the source, transformed preview, planned output filename, and destination before publishing separate images. Selected originals are never overwritten, regardless of the configured output policy. Existing destination collisions block publication rather than silently changing an approved filename.

### `photo-story`

```sh
kim_all photo-story [--] IMAGE...
```

Launches the dedicated Photo story editor directly, without the Image gallery versus Photo story chooser. Photo stories support sections, site previews, single-page or multiple-page publication, folder or ZIP destination, and mandatory Review Changes. The **Image gallery** choice instead opens the classic gallery interface, which has different controls.

### `gallery-choose`

```sh
kim_all gallery-choose -- IMAGE...
```

This is the current Dolphin **Create a gallery…** entry point. **Image gallery** launches the classic gallery creator through `gallery`; **Photo story** launches the three-panel Gallery Publishing editor. The editor provides Story order, an editable story canvas, and Gallery settings. It supports the gallery types **Travelogue**, **Photo essay**, **Illustrated story**, and **Simple gallery**; visual styles **Classic**, **Modern**, **Dramatic**, **Light**, and **Dark**; and image arrangements **One image**, **Up to two images**, **Adaptive**, **Justified**, and **Masonry**. Settings for captions and filenames are independent of image arrangement.

Use **Add heading** and **Add text** to write a photo story. Under **Website structure**, **Single page** creates a scrolling website with section links, while **Multiple pages** creates a home page and a page for each section. **Sections…** manages section titles, descriptions, optional image covers, and assignments of images and existing story text. Removing a section does not remove its images or text from the story. Unassigned images and story text are retained in either publication structure.

Choose **Gallery folder (recommended)** or **ZIP archive**, use **Preview in browser**, and inspect **Review Changes** before applying. Review includes the planned output directory, pages, viewer assets, generated images, collisions, and blocked items. Output creates a new destination and never overwrites originals or silently renames an approved target. A source change or late destination collision blocks publication. Generated gallery images omit embedded source metadata. The completed site can be opened locally and uploaded to a hosting service manually; KIMng does not publish to a remote host.

### `gallery`

```sh
kim_all gallery -- IMAGE...
```

This command opens the classic HTML gallery creator directly. Dolphin's **Create a gallery… → Image gallery** choice also invokes this workflow through [`gallery-choose`](#gallery-choose). The creator supports image ordering, captions, Clean Light and Dark Portfolio themes, Standard and High image resolution, column selection, and gallery preview. Choose **Photo story** for the separate story editor.

## Publishing your image gallery

A KIMng-generated gallery is a self-contained static website made of plain HTML, CSS, JavaScript, and JPEG images. It requires **no server-side runtime** (no PHP, Python, or Node.js on the server), **no database**, and **no external CDN dependencies**. KIMng does not upload galleries automatically; after generating a gallery folder (or extracting a generated ZIP archive), you can preview it locally or publish it to any static web host.

### Generated files and directory layout

Upload the **entire contents** of the generated gallery folder while keeping its directory structure intact:

- **Photo story** (`Create a gallery… → Photo story`):
  - `index.html` (and section `.html` pages when using **Multiple pages**)
  - `style.css`, `gallery-viewer.css`, `gallery-viewer.js`
  - `images/` containing the generated web-sized JPEG files (`0001.jpg`, `0002.jpg`, ...)
- **Classic Image gallery** (`Create a gallery… → Image gallery`):
  - `index.html` and generated stylesheet/navigation files
  - `images/` (web-sized images) and `thumbnails/` (gallery thumbnails)

All internal links and asset references use **relative paths** (for example, `style.css` and `images/0001.jpg`). Because no root-relative (`/images/...`) URLs are hardcoded, the same generated folder works both at a domain root (`https://example.com/`) and beneath a website subdirectory (`https://example.com/galleries/malta/`).

### Local preview with Python

To test a generated gallery over HTTP before uploading:

```sh
python3 -m http.server 8000 --directory /path/to/your-gallery
```

Then open `http://127.0.0.1:8000/` in a web browser. To test subdirectory hosting, serve the parent directory instead and open `http://127.0.0.1:8000/your-gallery/`. Press `Ctrl+C` in the terminal to stop the preview server.

### Hosting options

- **Traditional web hosting (SFTP or hosting control panel):** Connect with SFTP (or your host's file manager) and upload all files and subdirectories from the generated gallery folder into your web root (such as `public_html/`) or a subfolder (such as `public_html/galleries/trip/`).
- **GitHub Pages:** Create a GitHub repository, commit the contents of the generated gallery folder (`index.html` at the repository root or inside `docs/`), and enable **Settings → Pages** pointing to that branch and folder. Relative paths ensure the site works cleanly at `https://<user>.github.io/<repo>/`.
- **Cloudflare Pages:** Upload the generated gallery folder directly via Cloudflare Pages **Direct Upload** (drag-and-drop or Wrangler CLI), or connect a Git repository with no build command and the gallery folder as the output directory.
- **Netlify:** Drag and drop the generated gallery folder onto **Netlify Drop** in the dashboard, or deploy from a Git repository with an empty build command and the gallery folder as the publish directory.
- **Self-hosting with Apache or Nginx:** Copy the gallery folder into your server's document root (for example, `/var/www/html/galleries/trip/`). Ensure the web server user has read permissions on files (`0644`) and traverse permissions on directories (`0755`), and that `DirectoryIndex index.html` (Apache) or `index index.html;` (Nginx) is enabled. No rewrite rules or application proxies are needed.

### Updating an existing gallery

Because KIMng publishes each new export into a fresh destination directory rather than overwriting an existing gallery, update a hosted site by generating a new gallery folder locally and then replacing the remote folder's contents (for example, syncing with `rsync --delete` over SSH/SFTP, uploading a new Cloudflare Pages / Netlify deploy, or pushing an updated commit to GitHub Pages). Removing stale files on the remote host prevents orphaned old images from remaining publicly accessible.

### Metadata and location privacy

Generated **Photo story** gallery images omit embedded source EXIF, IPTC, XMP, and GPS metadata. However, visible scene details, landmarks, faces, captions, titles, and visible filenames (if shown) can still reveal identifying or location information. Always review the generated gallery locally before publishing it publicly.

*Future design note:* Static gallery hosting conventions here were informed by [Fussel](https://github.com/cbenning/fussel), and the [Fussel demo gallery](https://benninger.ca/fussel-demo/) is recorded as a visual presentation reference for a future KIMng gallery presentation milestone. KIMng does not require or depend on Fussel.

### `location-gpx`, `location-copy`, `location-apply`, `location-report`, `location-reduce`

```sh
kim_all location-gpx -- IMAGE...
kim_all location-copy -- IMAGE...
kim_all location-apply -- IMAGE...
kim_all location-report -- IMAGE...
kim_all location-reduce -- IMAGE...
```

These are separate location/GPS dispatcher routes. `location-gpx` locates images using a GPX track; `location-copy` derives location data from a reference image; `location-apply` offers manual or map-based coordinate assignment; `location-report` inspects existing location metadata without requesting a write; and `location-reduce` plans approximate coordinates to reduce precision. Supported modifying workflows present a review before applying changes and do not treat inspection as permission to write. Use the Dolphin **Location/GPS** menu for guided input selection and map controls. GPS removal is a separate `stripmeta --mode gps` workflow.

**GPS publication limits:** Location-changing commands operate on verified nonanimated still JPEG, PNG, WebP, TIFF, HEIC/HEIF, or AVIF with matching extensions. Progressive JPEG, animated APNG/WebP, PSD, RAW, and unsupported containers are refused for GPS writing. The read-only location report can inspect metadata without authorizing any edit. See [format limitations](FORMATS.md#gps-metadata-writer-restrictions).

### `metadata-view`

```sh
kim_all metadata-view -- IMAGE...
```

Opens one read-only Metadata Browser window containing the entire selection in order, including images from different directories. The Compare view supports Left and Right image selectors and drag-and-drop assignment, so you can choose the comparison pair after opening Browser. Requires Python 3 with PySide6 and ExifTool. Does not prompt for output policy or publish files.

### `metadata-edit`

```sh
kim_all metadata-edit -- IMAGE...
```

Opens one Metadata Editor window containing the entire selection of supported images. PDF input is not an editable image here and is rejected; the read-only Metadata Browser can inspect supported PDF metadata. This is a read-only change planner: drafts are retained when navigating images, and review does not write image metadata or XMP sidecars. Requires Python 3 with PySide6 and ExifTool. Does not prompt for output policy or publish files.

### `pdf-pages`

~~~sh
kim_all pdf-pages -- DOCUMENT.pdf [DOCUMENT2.pdf ...]
~~~

**Convert PDF pages to images…** renders pages from selected PDF documents into separate image files. This is different from extracting image objects already embedded in a PDF.

The interactive dialog lets you choose an output image format and inspect the planned results before applying them.

The default destination is **Beside each source**. You can instead select a shared output directory.

Review Changes lists the planned inputs, pages, filenames, destinations, actions, and statuses. Known filename conflicts are resolved while preparing the review. If an approved output filename becomes occupied afterward, publication is blocked rather than silently renamed.

The source PDFs are not overwritten. Rendering uses Poppler utilities, including `pdfinfo` and `pdftoppm`.

### `pdf-extract`

~~~sh
kim_all pdf-extract -- DOCUMENT.pdf [DOCUMENT2.pdf ...]
~~~

**Extract embedded images from PDF…** extracts image resources stored inside selected PDF documents. Unlike `pdf-pages`, it does not render each complete PDF page as an image.

The action uses Poppler's `pdfimages` utility and provides an interactive Review Changes step.

The default destination is **Beside each source**, with an option to choose a shared output directory.

Review Changes identifies planned outputs and any blocked items. Known filename conflicts are resolved during planning. Late collisions, changed sources, and changed approved destinations block unsafe publication.

Extraction creates separate output files and does not modify the source PDFs. Extraction results depend on the image resources actually present in each PDF.

### `print`

```sh
kim_all print -- IMAGE...
kim_all print OUTPUT_DIRECTORY IMAGE...
```

Prompts for one of seven print layouts and an output PDF. Layouts specify paper orientation, physical print dimensions, or thumbnail grid. Presets 2, 3, and 4 use A3 portrait pages; other presets use A4 landscape or portrait pages. The optional first argument chooses the initial destination directory. Result is validated as an ordered, multi-page PDF.

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
| `spacestounderscore` | Replace spaces with underscores in filename stems. |
| `underscorestospace` | Replace underscores with spaces in filename stems. |
| `interactive` | Display a dialog to choose a rename operation. |

**Interactive Rename:** The dialog offers **Create renamed copies (originals untouched)** and **Rename selected originals (confirmation required)**. Creating copies retains the original filenames and files. Renaming selected originals changes their filesystem names only after explicit confirmation. Neither operation re-encodes image content. The planned current and proposed filenames are displayed before applying changes. Conflicting destinations are checked before publication; existing unrelated files are not silently replaced.

EXIF-date formats include `YYYYMMDD_HHMMSS`, `YYYY-MM-DD_HH-MM-SS`, `YYYY-DD-MM_HH-MM-SS`, and `IMG-YYYYMMDD_HHMMSS`.

Sequential mode prompts for a base name, starting number, and minimum number width (1–18). Supported modes allow a separate output directory.

KIMng checks the complete batch for naming conflicts before making changes. Occupied paths are not overwritten. Cross-device moves copy and validate the bytes and metadata before publishing without clobbering and removing the unchanged source.

### `resize`

```sh
kim_all resize --size GEOMETRY [--output-dir DIR] -- IMAGE...
kim_all resize --percent PERCENT [--output-dir DIR] -- IMAGE...
kim_all resize --custom -- IMAGE...
kim_all resize --custom-percent -- IMAGE...
```

Geometry uses ImageMagick’s supported resize grammar and preserves aspect ratio for the menu presets. Percentage is an integer 1–1000; 100% keeps dimensions, values above 100% explicitly enlarge. ImageMagick rounding is used, with dimensions clamped to at least one pixel. Existing presets are maximum width/height bounds, not forced exact dimensions. Allow enlargement is off by default, so preset resizing does not upscale smaller images unless you explicitly enable that option. Percentage values above 100% request enlargement. Create mode uses `_resized`; authorized overwrite replaces only after validation. Animated APNG input is refused without changing the original, rather than risking silent frame loss; ordinary PNG is supported.

### `resizeandsend`

```sh
kim_all resizeandsend [--size full|WIDTHxHEIGHT] -- IMAGE...
```

**Send via email…** opens the email settings dialog even when `--size` is supplied. The argument supplies an initial size selection rather than bypassing the graphical workflow. Available choices include full size, 1600, 1200, 800 and 600 pixel square bounds, and custom dimensions.

Supported mail integrations include KMail, Thunderbird, Thunderbird (Flatpak), and `xdg-email`, subject to local availability. If no supported client is available, preparation is blocked.

Full-size preparation copies the original bytes. Animated APNG cannot be resized for email because animation frames may be lost.

The prepared attachments must pass Review Changes before handoff. KIMng warns when attachment sizes exceed 18 MiB and blocks handoff above 25 MiB. A preparation failure for any selected image blocks handoff of the entire batch.

Attachments are retained under `${XDG_DATA_HOME:-$HOME/.local/share}/kimng/email-attachments` because mail clients may read them asynchronously.

KIMng does not automatically delete prepared attachments. Remove them from the attachment directory when they are no longer needed. Email preparation creates temporary attachment copies, not a published derivative meant to replace the original image. The selected mail program controls the final sending step. A failed mail-client launch does not authorize KIMng to alter the source files. If mail-client handoff fails after preparation, retained attachments may be available for manual attachment.

### `rotate`

```sh
kim_all rotate --angle DEGREES [--preview] -- IMAGE...
kim_all rotate --exif [--preview] -- IMAGE...
kim_all rotate --custom [--preview] -- IMAGE...
```

Rotates by a supported signed decimal angle, auto-orients using EXIF, or prompts for a custom angle. Create mode publishes transformed copies. Overwrite mode replaces selected originals only after two-stage confirmation and output validation. Rotation preserves modification timestamps, including nanoseconds where supported, and validates image profiles and frame content. With `--preview`, rotation opens the interactive Qt planning workflow for the selected images before publication.

### `rotatewithexif`

```sh
kim_all rotatewithexif IMAGE...
```

Retained dispatcher alias for EXIF-based orientation. The Dolphin menu uses `rotate --exif`.

### `stripmeta`

```sh
kim_all stripmeta [--mode all|gps|ai] [--remove-ai] [--interactive] -- IMAGE...
```

Default mode `all` removes ordinary metadata fields while deliberately preserving embedded ICC color profiles and EXIF Orientation. It is not a byte-level removal of every metadata field. KIMng validates the resulting image and retained profile information before publication. `gps` removes recognized coordinate fields; `ai` removes recognized AI-generation fields, including IPTC AI prompts, prompt-writer name, AI system and AI system version. The DigitalSourceType field is removed only when it contains a recognized AI classification, not an unrelated classification. `--remove-ai` combines recognized AI-field removal with `all` or `gps`. Interactive mode selects a mode. GPS removal targets recognized coordinate fields; other metadata and visible scene details may still reveal a location. AI removal targets recognized AI-generation metadata, not every possible generator indicator. Unrecognized generator-specific fields and signed C2PA / Content Credentials may remain. ExifTool cannot guarantee their complete removal.

### `tiffjoin`

```sh
kim_all tiffjoin [--output PATH] [--] IMAGE...
```

Joins selected images/frames in selection order into a multi-page TIFF. Prompts for output when `--output` is omitted. Always creates a new file, regardless of `KIM_POLICY`; occupied names are numbered without replacing existing targets. Sources are preserved; output is staged and validated.

### `timeshift`

```sh
kim_all timeshift --offset [+|-]HH:MM:SS [--fields all|capture] -- IMAGE...
kim_all timeshift --interactive -- IMAGE...
```

Adds or subtracts the fixed offset from camera date tags. `all` (default) shifts `DateTimeOriginal`, `CreateDate`, and `ModifyDate`; `capture` shifts only `DateTimeOriginal`. Subsecond and timezone-offset tags remain unchanged, as do GPS timestamps and filesystem modification time. This shifts a camera’s wall-clock values; it does not convert time zones or reinterpret local time as UTC. With `--interactive`, the unified Qt date dialog handles the selected images. Date-action output labels such as `_dated` and `_location` are not controlled by the general Output Filenames affix settings.

### `webexport`

```sh
kim_all webexport [--custom] [--size WIDTHxHEIGHT] [--quality 1..100] [--format jpg|jpeg|png|webp|avif|keep] [--jpeg-progressive|--jpeg-baseline] [--jpeg-optimize] [--color srgb|preserve] [--output-dir DIR] -- IMAGE...
```

Use `--custom` to open custom Web Export settings. Web Export accepts an output directory and selected source files. The default destination is beside each source. Review Changes presents the planned filenames and destinations before processing. Default size is 1600×1600, default quality is 95 for JPEG, WebP and AVIF (independently configurable in Settings), format defaults to `KIM_WEB_FORMAT` (normally JPEG), and color defaults to ICC-managed sRGB. `keep` retains source format when supported. Web Export creates distinct derivatives, fits images within the specified dimensions without upscaling, and applies ImageMagick's `-strip` metadata policy. A compatible ICC profile can be retained or reapplied according to the selected color mode. Animated APNG input is refused rather than flattened. JPEG scan and optimization options apply only to JPEG output.

With `--color srgb` (the default), tagged images undergo ICC conversion to sRGB. Untagged RGB images are treated as sRGB, while ambiguous untagged CMYK images are rejected. Color-managed conversion requires an installed sRGB profile and the appropriate source profile. `--color preserve` retains embedded color profiles where supported.

## Video actions

### `slideshow`

```sh
kim_all slideshow [--seconds-per-photo 1..30] [--size WxH] [--fps 1..30] [--background COLOR] [--output FILE] [--interactive] -- PHOTO...
```

Creates a derived, silent H.264/yuv420p MP4. The interactive action uses one settings dialog for timing, resolution, frame rate, background (including custom `#RRGGBB`), destination and estimated duration. Images may be added and reordered regardless of the initial selection, up to the 200-image limit. The interactive slideshow dialog also has a selected-slide preview and a playback timestamp readout for checking image order and timing. Interactive rendering preserves the order established in the slideshow dialog. Noninteractive input uses natural filename ordering. Images are fitted without upscaling and padded. Defaults: 3 seconds per image, 1280×720, 25 fps, black background. Size presets are 854×480, 1280×720 and 1920×1080. Limits: 200 images, 600 seconds, 18,000 frames and 1920×1080. The output must be a free `.mp4` path; existing files are not replaced. RAW, layered, vector, HDR and animated sources are rejected. H.264 encoder `libx264` is required.

Slideshows do not include titles, transitions, pan, or zoom effects. They are intended for straightforward photo-to-video conversion, not video editing.

### `video`

```sh
kim_all video --size hd720|hd1080 --crf 17|23|29 --codec libx264|libx265 --container orig|mp4 -- VIDEO...
kim_all video --size hd720|hd1080 --codec av1 --av1-quality high|balanced|smallest|custom --container orig|mp4 -- VIDEO...
```

Dolphin exposes six MP4 presets for each of H.264 and H.265 (720p/1080p with three quality choices). Original-container output remains available through the CLI. For AV1 encoding, KIMng uses `libsvtav1` when available or `libaom-av1` otherwise. If neither encoder is available, the operation fails rather than substituting H.264 or H.265. AV1 High uses CRF 28 with speed 6, Balanced uses CRF 35 with speed 8, and Smallest File uses CRF 42 with speed 8. For `libsvtav1`, KIMng passes the speed as `-preset`; for `libaom-av1`, it uses `-cpu-used` with `-b:v 0`. Lower speed values generally favor encoding efficiency over speed, but processing time and output size depend on the input and encoder. AV1 CRFs are not directly comparable to H.264/H.265 CRFs. `custom` prompts for AV1 quality and speed through the CLI; the Dolphin AV1 menu offers six MP4 presets. Original-container mode fails when codecs/streams are incompatible instead of forcing MP4. Aspect ratio and orientation are handled; no unnecessary upscaling.

### `videoaudio`

```sh
kim_all videoaudio --mode extract --format m4a|mp3|flac|wav -- VIDEO...
kim_all videoaudio --mode mute -- VIDEO...
kim_all videoaudio --interactive -- VIDEO...
```

Extracts the first audio stream to the selected container; additional audio streams are not silently claimed as exported. **M4A** stream-copies compatible AAC, otherwise encodes AAC at 192 kb/s. **MP3** uses `libmp3lame` at variable-bitrate quality `-q:a 2`; **FLAC** uses lossless FLAC; **WAV** uses 16-bit uncompressed PCM (`pcm_s16le`). These are output settings, not a promise of a particular file size.

In **Remove audio** mode, KIMng creates a separate video without audio tracks. The video stream is copied without re-encoding, preserving its original quality. If the source video has no audio, no new file is created.

The Remove audio workflow opens **KIMng - Review remove audio** before publication. The review presents the planned outputs and allows a shared destination directory or **Beside each source**. Changing the destination updates the reviewed plan. The selected source videos are preserved.

Use `--interactive` to open the available audio settings workflow. Extract audio and Remove audio have different publication behavior; do not assume the Remove audio review dialog also applies to audio extraction.

### `videoframes`

```sh
kim_all videoframes --mode single --at HH:MM:SS[.sss] [--format png|jpg] -- VIDEO...
kim_all videoframes --mode thumbnail [--format png|jpg] -- VIDEO...
kim_all videoframes --mode contact [--grid 3x3|4x4|5x5] [--format png|jpg] -- VIDEO...
kim_all videoframes --interactive -- VIDEO...
```

Extracts one frame, a representative midpoint thumbnail (not frame zero), or one labeled contact sheet. Contact sheets use 320×180 fit/pad tiles, sample evenly over duration, and may repeat positions for short videos. Display rotation is applied.

The interactive single-frame workflow opens **KIMng - Extract frame options**, a Qt dialog with per-video timestamps, a shared output format, and an option to apply one timestamp to all selected videos. It is not a standalone timestamp prompt. Video contact sheets have a separate Qt settings dialog for grid and image format.

Before publishing extracted frames, thumbnails, or video contact sheets, KIMng opens **KIMng - Review video frames**. The review shows planned outputs and supports **Beside each source** or a shared destination directory. Changes to the destination require the output plan to be reviewed again. Extracted results are separate files; the original video files remain untouched.

### `videogif`

```sh
kim_all videogif --start HH:MM:SS[.sss] --duration SECONDS --fps 10|12|15|24 --width 320|480|640|800 --loop infinite|once -- VIDEO...
kim_all videogif --interactive -- VIDEO...
```

Creates a palette-optimized GIF for the requested interval. Duration is greater than zero and at most 15 seconds, with at most 360 nominal frames and a 200-million output pixel-frame work bound. Width is a maximum and does not upscale; height follows aspect ratio. At least two output frames are required. Infinite uses GIF loop extension 0; once omits looping.

Use `--interactive` to open **KIMng - Animated GIF**, the Qt settings dialog for start time, duration, frame rate, output width, and looping. This is separate from the video frame-extraction Review Changes workflow.

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

Opens the installed HTML User Guide. In a normal local session, KIMng tries `xdg-open` first, then its standalone Qt viewer as a fallback. In an SSH session, it prefers the internal viewer to avoid a browser detaching without displaying a visible window. If Qt WebEngine is unavailable, the viewer can offer to open the guide in the system browser.

### `settings`

```sh
kim_all settings
```

Opens the graphical KIMng settings dialog. No selected files are required.

## Troubleshooting

If an action fails, check the final KDialog report. Confirm that the source is readable, the destination is writable, and the required ImageMagick coder, FFmpeg encoder, or other dependency is installed.

When running `kim_all` directly, inspect the terminal output for diagnostics. Previously completed outputs remain available if a later batch item fails.

Test uncertain operations using disposable copies and `KIM_POLICY=create`, not important originals. See [FORMATS.md](FORMATS.md) for codec support and [INSTALL.md](../INSTALL.md) for missing Dolphin menus or installation problems.
