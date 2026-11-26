
# Image and Video Format Support

KIMng uses the installed ImageMagick 7 build, ExifTool, FFmpeg, and ffprobe. A recognizable extension does not guarantee that a decoder or encoder is available. KIMng checks required capabilities and validates generated output; if an encoder is unavailable, the operation fails rather than silently selecting another format.

## Image Formats

| Format | Reading | Writing | Important limitations |
|---|---|---|---|
| JPEG/JPG/JFIF | ImageMagick JPEG decoder | JPEG encoder; compression and conversion menus | Lossy compression. Progressive/baseline scans and Huffman optimization are JPEG-specific. JFIF is a JPEG variant. |
| PNG | ImageMagick PNG decoder | PNG encoder | Standard PNG conversion does not imply APNG animation support. Embedded ICC profiles are handled where supported. |
| APNG | PNG animation control detection and FFmpeg/ffprobe inspection | FFmpeg APNG conversion and animation creation | APNG conversion and creation validate frames, timing, and looping. The creator requires 2–360 single-frame images and normalizes them to a transparent canvas. **Animated APNG input is refused by Resize, Web Export and resized email preparation** because an ImageMagick decoder may expose only the first frame. Normal still PNG remains supported. |
| GIF | ImageMagick GIF decoder | GIF encoder; `animate` creates GIF animations | Indexed color; frame count, delays, and looping are validated for animation operations. |
| TIFF/TIF | ImageMagick TIFF decoder | TIFF encoder; `tiffjoin` creates multi-page files | Multiple pages are supported where the selected operation permits them. |
| BMP/DIB | ImageMagick BMP decoder | BMP encoder; menu selects BMP5 | Normally single-frame. DIB is treated as a BMP alias; no general ICC guarantee. |
| WebP | ImageMagick WebP decoder when installed | Runtime-probed WebP encoder | May contain animation; frame and ICC handling depend on the coder and operation. |
| AVIF | ImageMagick AVIF coder/delegate when installed | Runtime-probed AVIF encoder | Support depends on the installed AV1 delegate. Multi-frame and ICC handling are checked where applicable. |
| HEIC/HEIF | ImageMagick HEIC/HEIF decoder when installed | Runtime-probed HEIC encoder | May contain multiple images. No silent substitution with AVIF or JPEG. |
| JPEG XL (JXL) | Optional JXL decoder | Optional JXL encoder | Reading and writing require separately available codec support. KIMng checks encoder availability at runtime and rejects unsupported conversions without publishing an output. |
| JPEG 2000 (JP2/J2K/JPC/J2C) | ImageMagick JPEG 2000 coder/delegate | Runtime-probed JPEG 2000 encoder | JP2 offers lossless/lossy modes; lossless uses delegate `rate=1`. Lossy quality is codec-specific, not equivalent to JPEG quality. |
| ICO/CUR | ImageMagick icon decoder when installed | Custom conversion if writing is supported | Files may contain several icon sizes or images. Do not assume a lossless single-image round trip. |
| PNM family (PBM/PGM/PPM/PAM/PNM) | ImageMagick decoder | Available PNM coders | Typically still images with limited profile and metadata support. |
| SVG/SVGZ | Rasterized through the installed SVG delegate and security policy | Coder-dependent; conversion is primarily raster-oriented | Rasterization loses vector structure. Do not weaken delegate security restrictions for untrusted files. |
| PDF | ImageMagick PDF delegate when local policy allows | Validated PDF output; `album` and `print` generate PDFs | Page count and layout are checked. Untrusted PDF input remains subject to local delegate/security policy. |
| PSD | KIMng Photoshop source preparation for supported photo workflows | No PSD output | Supported 8- or 16-bit RGB, grayscale, or profiled CMYK PSD input, subject to canvas and decoding limits. Layers are rendered, not retained as an editable document. Recipes require a supported output format. |
| PSB | Rejected | Not supported | Large Photoshop Document (PSB) files are explicitly refused; do not assume they are interchangeable with PSD. |
| Radiance HDR / OpenEXR | Coder-dependent decoder | Coder-dependent encoder | Direct conversion and slideshow workflows reject HDR/OpenEXR input. No automatic HDR-to-SDR tone mapping is promised. |
| Camera RAW (DNG, CR2/CR3, NEF, ARW, RAF, ORF, RW2, others) | Installed ImageMagick RAW delegate, if available | No dedicated RAW development or output workflow | Demosaicing and color depend on the delegate. RAW metadata editing is rejected; conversion must not overwrite RAW originals. Use a dedicated RAW processor for development. |

## Photoshop PSD Inputs

KIMng accepts supported Photoshop PSD files as **read-only sources** for applicable image actions, including Recipes and supported publication workflows. **PSB is not supported.** PSD preparation accepts supported 8- and 16-bit grayscale, RGB and profiled CMYK documents within its limits of 30,000 pixels per dimension, 100 megapixels, and a 2 GiB source-file size. A PSD is prepared as a rendered image for processing. This is not an editable Photoshop round trip: layers and other document-specific structure are not reproduced in the derivative.

**Recipes never save PSD output.** If a recipe cannot determine an output format for a PSD, the Run a Recipe preflight stops and offers **Fix recipe…**, where **Convert Format** can be added and a supported format selected. KIMng does not automatically substitute JPEG or PNG. PSD source bytes remain unchanged.

For direct PSD-to-PDF conversion, `kim_all convert --format pdf --strip-metadata -- DOCUMENT.psd` is supported. The `--strip-metadata` conversion flag is not available for arbitrary formats or non-PSD inputs. Other metadata-removal workflows use the dedicated `stripmeta` action.

Some PSDs contain CMYK data, transparency, embedded ICC profiles, or higher bit depths. KIMng checks source and output capabilities and applies operation-specific profile, alpha, and precision handling. The output's format and properties must be inspected rather than assuming the source document's characteristics will be preserved identically.

For the full workflow, see [Recipes](RECIPES.md#photoshop-psd-inputs-and-fix-recipe).

## Frame Preservation

KIMng distinguishes still images, animations, and multi-page documents. Conversion rejects known frame loss rather than silently flattening unsupported animations. APNG has a dedicated FFmpeg path; other multi-frame formats depend on the installed coder and the selected action.

Operations that preserve frames validate expected input and output frame counts. A format's ability to contain multiple frames does not guarantee that every KIMng operation supports them.

**Animation-specific boundaries:** Animated GIF conversion checks frame delays and looping. APNG conversion has a dedicated FFmpeg path and checks animation control information. Animated WebP and other multi-frame formats require suitable installed coders and action-specific validation; do not assume that an ordinary resize or web export preserves every animation property. **Resize, Web Export and resized email attachments refuse animated APNG rather than publish a flattened still image. Full-size email preparation copies the original bytes.** This applies even when the file is named `.png` rather than `.apng`. Nonanimated PNGs work normally. Failed or unsupported operations leave existing source files untouched.

Direct conversion refuses multi-image AVIF/HEIC inputs and animated WebP conversion to non-WebP output rather than risking unsupported frame handling.

Multi-page TIFF and PDF inputs are documents rather than timed animations. Converting a multi-page or animated source to a single-image format is refused where frames would otherwise be discarded.

## Color Profiles and Metadata

Color handling depends on the selected action, usable ICC profiles, and output coder. Web export supports ICC-managed conversion to sRGB or preservation of compatible embedded profiles. Other actions have their own profile and metadata rules.

The default web-export color mode targets sRGB; `--color preserve` instead requests retention of a usable, compatible input profile. ICC validation cannot manufacture a profile that an encoder does not support, and color conversion may be rejected rather than silently drop a required profile. JPEG baseline/progressive scans and Huffman optimization are separate from ICC handling. KIMng does not promise automatic HDR-to-SDR tone mapping or universally lossless CMYK-to-RGB conversion. Metadata preservation also varies by format. GPS-only removal targets recognized coordinates but does not guarantee complete location anonymization. AI-only removal targets recognized AI-generation fields but may leave generator-specific metadata. Neither selective mode is equivalent to the full-strip operation. Full stripping removes ordinary metadata but intentionally retains ICC color profiles and EXIF Orientation to preserve essential image characteristics. Even full stripping cannot guarantee complete removal of signed C2PA / Content Credentials.

See [Web export](commandconfig.md#webexport) for color options and [File handling](commandconfig.md#output-and-file-handling) for preservation behavior.

### GPS metadata writer restrictions

GPS edits and precision reduction are limited to verified, nonanimated still JPEG, PNG, WebP, TIFF, HEIC/HEIF, or AVIF images whose extensions match their detected formats. Progressive JPEG is refused by the GPS writer because the current container verifier cannot preserve its scan structure. Animated PNG (APNG), animated WebP, PSD, camera RAW, and other unsupported containers remain read-only for these GPS changes. KIMng does not silently transcode a source to make it writable.

Progressive JPEG restrictions also apply to the metadata-writing paths used by `stripmeta`, `copyright`, `capturedate`, `timeshift`, and `datesync` when safe container verification is required.

Selective PNG metadata stripping (`stripmeta --mode gps` or `--mode ai`) refuses PNG files containing any `eXIf` chunk, not just malformed chunks. Other PNG metadata operations reject unsupported or malformed `eXIf` structures where applicable. These restrictions are operation-specific: format decoding and image conversion are distinct from safe metadata editing.

## Video Formats and Encoders

KIMng uses FFmpeg for H.264 (`libx264`) and H.265 (`libx265`) video. AV1 prefers `libsvtav1` and uses `libaom-av1` when SVT-AV1 is unavailable; it does not substitute another codec if AV1 encoding is unavailable. Available containers must support the selected codecs and streams. An incompatible original container causes an error rather than an automatic switch to MP4.

Video utilities use FFmpeg for frame extraction, midpoint thumbnails, contact sheets, audio extraction or removal, and GIF creation. Photo-to-MP4 slideshow generation creates a separate video using selected still images. Interactive rendering preserves the order established in the slideshow dialog; noninteractive rendering uses natural filename ordering. Encoders, stream-copy compatibility, resolution/quality options, GIF loop settings, and output validation depend on the operation and installed FFmpeg capabilities. See [Video actions](commandconfig.md#video-actions) for exact options and limits.

## Check Installed Capabilities

These commands inspect local support without changing system configuration:

```sh
magick -version
magick -list format
ffmpeg -hide_banner -encoders
ffprobe -version
exiftool -ver
```

The read/write flags in `magick -list format` show advertised capabilities of the installed build, not a guarantee that a particular conversion will succeed. Delegates, security policies, libraries, container compatibility, and individual file characteristics may still prevent an operation. KIMng checks relevant capabilities and validates outputs for the selected action.

## PDF source operations

KIMng supports two distinct operations on PDF input documents through **Convert/Compress**:

| Dolphin action | Command | Operation |
|---|---|---|
| Convert PDF pages to images… | `kim_all pdf-pages -- DOCUMENT.pdf` | Render complete PDF pages into separate images |
| Extract embedded images from PDF… | `kim_all pdf-extract -- DOCUMENT.pdf` | Extract image resources embedded in the PDF |

PDF page rendering depends on Poppler utilities such as `pdfinfo` and `pdftoppm`. Embedded-image extraction uses `pdfimages`.

Both actions open interactive settings and **Review Changes**. The default destination is beside each source PDF, with an optional shared directory.

Output filenames are established during review. Known conflicts may be resolved by numbering before approval; late collisions block publication instead of changing an approved output filename.

These are create-only PDF input operations. Neither modifies or overwrites the source PDF.

PDF input support is distinct from KIMng's ability to create PDFs from selected images.
