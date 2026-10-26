
# Image and Video Format Support

KIM6 uses the installed ImageMagick 7 build, ExifTool, FFmpeg, and ffprobe. A recognizable extension does not guarantee that a decoder or encoder is available. KIM6 checks required capabilities and validates generated output; if an encoder is unavailable, the operation fails rather than silently selecting another format.

## Image Formats

| Format | Reading | Writing | Important limitations |
|---|---|---|---|
| JPEG/JPG/JFIF | ImageMagick JPEG decoder | JPEG encoder; compression and conversion menus | Lossy compression. Progressive/baseline scans and Huffman optimization are JPEG-specific. JFIF is a JPEG variant. |
| PNG | ImageMagick PNG decoder | PNG encoder | Standard PNG conversion does not imply APNG animation support. Embedded ICC profiles are handled where supported. |
| APNG | FFmpeg/ffprobe inspection when PNG animation control data is present | FFmpeg APNG encoder | Frame count, timing, and looping are checked for APNG-to-APNG conversion. Unsupported frame loss is rejected. |
| GIF | ImageMagick GIF decoder | GIF encoder; `animate` creates animations | Indexed color; frame count, delays, and looping are validated for animation operations. |
| TIFF/TIF | ImageMagick TIFF decoder | TIFF encoder; `tiffjoin` creates multi-page files | Multiple pages are supported where the selected operation permits them. |
| BMP/DIB | ImageMagick BMP decoder | BMP encoder; menu selects BMP5 | Normally single-frame. DIB is treated as a BMP alias; no general ICC guarantee. |
| WebP | ImageMagick WebP decoder when installed | Runtime-probed WebP encoder | May contain animation; frame and ICC handling depend on the coder and operation. |
| AVIF | ImageMagick AVIF coder/delegate when installed | Runtime-probed AVIF encoder | Support depends on the installed AV1 delegate. Multi-frame and ICC handling are checked where applicable. |
| HEIC/HEIF | ImageMagick HEIC/HEIF decoder when installed | Runtime-probed HEIC encoder | May contain multiple images. No silent substitution with AVIF or JPEG. |
| JPEG XL (JXL) | Optional JXL decoder | Optional JXL encoder | Reading and writing require separately available codec support. KIM6 checks encoder availability at runtime and rejects unsupported conversions without publishing an output. |
| JPEG 2000 (JP2/J2K/JPC/J2C) | ImageMagick JPEG 2000 coder/delegate | Runtime-probed JPEG 2000 encoder | JP2 offers lossless/lossy modes; lossless uses delegate `rate=1`. Lossy quality is codec-specific, not equivalent to JPEG quality. |
| ICO/CUR | ImageMagick icon decoder when installed | Custom conversion if writing is supported | Files may contain several icon sizes or images. Do not assume a lossless single-image round trip. |
| PNM family (PBM/PGM/PPM/PAM/PNM) | ImageMagick decoder | Available PNM coders | Typically still images with limited profile and metadata support. |
| SVG/SVGZ | Rasterized through the installed SVG delegate and security policy | Coder-dependent; conversion is primarily raster-oriented | Rasterization loses vector structure. Do not weaken delegate security restrictions for untrusted files. |
| PDF | ImageMagick PDF delegate when local policy allows | Validated PDF output; `album` and `print` generate PDFs | Page count and layout are checked. Untrusted PDF input remains subject to local delegate/security policy. |
| PSD/PSB | ImageMagick decoder when installed | Coder-dependent; no dedicated menu output | Layers and document structure may be flattened. Use an editor for layer-preserving work. |
| Radiance HDR / OpenEXR | Coder-dependent decoder | Coder-dependent encoder | No promised automatic HDR-to-SDR color-managed conversion. `slideshow` rejects HDR input. |
| Camera RAW (DNG, CR2/CR3, NEF, ARW, RAF, ORF, RW2, others) | Installed ImageMagick RAW delegate, if available | No dedicated RAW development or output workflow | Demosaicing and color depend on the delegate. RAW metadata editing is rejected; conversion must not overwrite RAW originals. Use a dedicated RAW processor for development. |

## Frame Preservation

KIM6 distinguishes still images, animations, and multi-page documents. Conversion rejects known frame loss rather than silently flattening unsupported animations. APNG has a dedicated FFmpeg path; other multi-frame formats depend on the installed coder and the selected action.

Operations that preserve frames validate expected input and output frame counts. A format's ability to contain multiple frames does not guarantee that every KIM6 operation supports them.

## Color Profiles and Metadata

Color handling depends on the selected action, usable ICC profiles, and output coder. Web export supports ICC-managed conversion to sRGB or preservation of compatible embedded profiles. Other actions have their own profile and metadata rules.

See [Web export](commandconfig.md#webexport) for color options and [File handling](commandconfig.md#output-and-file-handling) for preservation behavior.

## Video Formats and Encoders

KIM6 uses FFmpeg for H.264 (`libx264`) and H.265 (`libx265`) video. AV1 prefers `libsvtav1` and uses `libaom-av1` when SVT-AV1 is unavailable; it does not substitute another codec if AV1 encoding is unavailable. Available containers must support the selected codecs and streams. An incompatible original container causes an error rather than an automatic switch to MP4.

Video utilities use FFmpeg for frame extraction, contact sheets, audio extraction or removal, and GIF creation. See [Video actions](commandconfig.md#video-actions) for preset choices, supported audio outputs, encoding settings, and operation-specific limits.

## Check Installed Capabilities

These commands inspect local support without changing system configuration:

```sh
magick -version
magick -list format
ffmpeg -hide_banner -encoders
ffprobe -version
exiftool -ver
```

The read/write flags in `magick -list format` show advertised capabilities of the installed build, not a guarantee that a particular conversion will succeed. Delegates, security policies, libraries, container compatibility, and individual file characteristics may still prevent an operation. KIM6 checks relevant capabilities and validates outputs for the selected action.
