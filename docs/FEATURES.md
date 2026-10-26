# KIM6 features

KIM6 provides short, batch-friendly operations in Dolphin’s context menus. This guide describes what the current dispatcher does; it does not promise that every ImageMagick format or optional codec exists on every system. The [complete 107-entry menu inventory](ACTIONS.md) is authoritative for visible labels and arguments. Exact options are in [commandconfig.md](commandconfig.md).

## Image preparation

### JPEG compression

Choose a JPEG quality preset or custom value (1–100). Compression is lossy; the quality number is not a percent size reduction. Progressive scan is the established default. Baseline scan is available explicitly. Huffman optimization can change file size but cannot promise a reduction and is not a claim of losslessness.

### Resize

Resize presets constrain the image within a square bound while preserving aspect ratio; they do not force every photo to square dimensions. Custom ImageMagick geometry is also supported. Percentage resize accepts 1–1000%, including explicit enlargement; it uses ImageMagick rounding and limits output dimensions to at least one pixel. EXIF orientation is respected.

### Convert

The menu exposes JPEG, PNG, GIF, BMP5, TIFF, PDF, WebP, AVIF, HEIC/HEIF, JPEG XL, and JPEG 2000. Custom format supports other ImageMagick coders where the installed build can actually encode them. JPEG 2000 has separate lossless/lossy choices; its quality values are not JPEG quality. Output format and extension are checked. Animated input is retained only when the selected conversion can validate all frames; KIM6 rejects unsupported flattening.

### Rotate and flip

Rotate by 90°, 180°, 270°, or a custom angle; auto-orient from EXIF; flip vertically or flop horizontally. These operations explicitly replace the selected image after staging and validation, independent of `KIM_POLICY`. Rotation preserves the original modification time; flip/flop produce changed content with a fresh time. They do not publish partial producer output.

## Web and email

Web export resizes and encodes a derivative with configurable quality and format. It never overwrites a source, even when `KIM_POLICY=overwrite`. Default color handling performs a real ICC conversion to sRGB for tagged sources, assumes untagged RGB is sRGB, and rejects ambiguous untagged CMYK. Preserve-profile mode keeps an embedded profile where supported. An installed sRGB profile and source profiles are required for managed transformations.

Email resize can attach full-size copies, 1600/1200/800/600/300 square-bounded derivatives, or a custom size. Only successful files are attached. Attachments persist in the reported KIM6 attachment folder after a client handoff because clients can read them asynchronously. Delete that folder manually after use. If no mail client exists, KIM6 reports the persistent folder for manual attachment.

## Metadata, names, and dates

- Full metadata stripping is the default for `stripmeta`; GPS-only and recognized AI-field modes are explicit alternatives. GPS removal is not complete location anonymization. Generic software tags are not treated as proof of AI generation. Signed C2PA credentials may remain.
- Copyright editing updates selected creator, copyright, and usage-rights fields through ExifTool; empty fields mean “leave unchanged.” A `{YEAR}` notice uses capture year or current-year fallback.
- Camera-time shift applies a fixed signed offset to `DateTimeOriginal`, `CreateDate`, and `ModifyDate` by default, or capture time only. It is not time-zone conversion.
- Date synchronization can set file mtime from `DateTimeOriginal`, or write EXIF dates from filesystem mtime. Time-zone-less camera time is treated as local, not UTC. Filesystem creation/birth time is not changed.
- Rename supports sequential numbering, text replacement, case and spacing changes, prefixes/suffixes, and EXIF-date formats. Cross-filesystem moves are validated byte copies followed by safe source removal; conflicts are preflighted.

Metadata-only operations preserve image pixels and filesystem mtime, including available nanosecond precision. This differs intentionally from transformations and transcoding. Read [commandconfig.md](commandconfig.md) and [SAFETY.md](SAFETY.md) before changing output policy.

## Albums, galleries, and animation

- **HTML gallery:** creates a self-contained output directory with resized main images, thumbnails, escaped links and relative assets; supports mixed source directories and opens the result in a browser when possible.
- **Collage:** assembles selected images into a PNG canvas with tile geometry, overlap, color, border, rotation, randomized rotation, seed and shadow choices.
- **PDF album:** eight page/layout choices.
- **Print PDF:** seven page and physical print-layout choices.
- **TIFF join:** creates a multi-page TIFF in selection order.
- **GIF animation:** combines selected still images in selection order, with delay and loop settings.

These are convenience outputs, not page-layout or photo-editing applications. They are staged and validated before publication.

## Video

Transcode presets cover 720p/1080p, H.264/H.265, CRF 17/23/29, and original-container/MP4 choices (24 combinations). Five AV1 choices use encoder-specific settings: SVT-AV1 is preferred, libaom-av1 is a capability fallback, and there is no fallback to another codec. A requested original container that cannot carry the selected streams/codecs fails rather than silently becoming MP4.

Video tools can extract a single frame, make a midpoint thumbnail, produce a labeled contact sheet, export the first audio stream, remove audio by stream-copy remux, or encode a video interval as a palette-optimized GIF. Mute does not re-encode the video. `videogif` differs from `animate`: it creates an animation from a video interval, while `animate` uses still images.

The photo-to-MP4 slideshow is intentionally simple: naturally sorted photos, fixed duration per image, fit/pad, H.264 MP4, no audio, titles, transitions, pan, or zoom. It is not a video editor.

## Output and preservation

Create mode numbers colliding outputs rather than replacing occupied entries. Explicit overwrite is available only to actions with that policy; `KIM_POLICY` never turns a derived-only action into source replacement. Selected sources are checked for aliases, symlinks or hardlinks where they would make replacement ambiguous. See [SAFETY.md](SAFETY.md) for action-specific mtime/metadata distinctions and the guarantees’ limits.
