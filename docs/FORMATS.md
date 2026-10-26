# Image and video format support

KIM6 uses the installed ImageMagick 7 build, ExifTool, FFmpeg and ffprobe. A readable extension does not prove that an encoder is available. For output formats, KIM6 checks the requested encoder/coder and validates actual bytes; missing encoders fail closed. The tables describe KIM6’s support shape, not a promise that every codec exists on every distribution.

## Image formats

| Format | Read/import | Write/export | Frames and color | Notes |
|---|---|---|---|---|
| JPEG/JPG/JFIF | ImageMagick decoder | JPEG coder; menu compression and conversion | Still images; ICC is handled where embedded and supported | Compression is lossy. Progressive/baseline and Huffman optimization are JPEG-specific. JFIF aliases JPEG. |
| PNG | ImageMagick decoder | PNG coder | Still PNG; embedded ICC where supported | Standard PNG conversion does not imply APNG animation. |
| APNG | Detected and inspected through FFmpeg/ffprobe when the PNG animation control chunk is present | FFmpeg APNG encoder when available | Frame count, timings and loop are checked for APNG-to-APNG; ICC depends on stream/coder support | Conversion to an output that cannot preserve frames is rejected rather than flattened. |
| GIF | ImageMagick decoder | ImageMagick GIF encoder; `animate` creates GIFs | Multi-frame animation, delays and looping are validated for animation operations | Palette and timing limits apply; GIF is indexed color. |
| TIFF/TIF | ImageMagick decoder | TIFF coder; `tiffjoin` creates ordered multi-page TIFF | Multi-page; ICC may be preserved | Supported as a multi-frame input/output where the selected action permits it. |
| BMP/DIB | ImageMagick decoder | BMP coder; menu explicitly requests BMP5 | Normally still; no general ICC guarantee | DIB is treated as a BMP alias. |
| WebP | ImageMagick coder when installed | Runtime-probed WebP encoder | May be animated; selected conversion/export checks frame handling | ICC depends on installed coder and selected operation. |
| AVIF | ImageMagick coder/delegate when installed | Runtime-probed AVIF encoder | Multi-frame handling is checked; ICC supported by format/coder where available | Availability depends on ImageMagick build and AV1 delegate. |
| HEIC/HEIF | ImageMagick coder/delegate when installed | HEIC encoder runtime-probed for both HEIC/HEIF naming | May contain multiple images; ICC depends on delegate | Not guaranteed by extension. No silent substitution with AVIF/JPEG. |
| JPEG XL (JXL) | Decoder only when JXL read support is present | Encoder only when JXL write support is present | ICC supported where coder permits | The project’s development test environment lacks the optional JXL encoder, so its real-encoder test skips there. Other systems may provide it. |
| JPEG 2000 JP2/J2K/JPC/J2C | ImageMagick JPEG 2000 coder/delegate when installed | Runtime-probed coder; JP2 lossless/lossy modes and J2K/JPC where supported | ICC supported where coder permits; frame handling depends on coder | Lossless JP2 uses delegate rate=1 and is pixel-tested when encoder exists. Lossy quality is codec-specific, not a JPEG quality percentage. |
| ICO/CUR | ImageMagick coder when installed | Custom output only if the coder advertises write support | May represent multiple icon sizes/images; KIM6 treats preserved frames as a requirement for supported conversions | Do not assume a single image or lossless round trip. |
| PNM family (PBM/PGM/PPM/PAM/PNM) | ImageMagick decoder | Available standard coders/custom output | Typically still; limited profile/metadata semantics | Useful interchange formats; not all preserve color metadata. |
| SVG/SVGZ | Rasterized only through the installed ImageMagick SVG delegate/policy | A vector output may be offered by a coder, but conversion workflows are principally raster-image operations | Rasterization can discard vector structure and profile semantics | Treat untrusted SVG cautiously. The local delegate/security policy governs external resources; do not loosen it to process arbitrary documents. |
| PDF | ImageMagick PDF delegate when local policy permits | PDF output is validated as a document with expected pages | May represent multiple pages; page dimensions/layout are checked for album/print | Input parsing is conservatively governed by local ImageMagick policy and delegates. Do not relax policy for untrusted PDFs. |
| PSD/PSB | ImageMagick decoder when installed | Coder-dependent; not advertised as a dedicated output | Layer/composite selection may flatten document structure | Conversion is not a lossless layered-document round trip. Use an editor for layer-preserving work. |
| Radiance HDR / OpenEXR | Coder-dependent decoder | Coder-dependent encoder | HDR range/color and ICC behavior vary | KIM6 does not promise automatic, color-managed HDR-to-SDR development. Slideshow rejects HDR input rather than silently tone-mapping it. |
| Camera RAW (DNG, CR2/CR3, NEF, ARW, RAF, ORF, RW2, others) | Only when the installed ImageMagick delegate can decode it | No RAW development engine; conversion may be possible only as a decoder-mediated derivative | Camera color, demosaicing and metadata depend on the delegate | RAW metadata editing is rejected; never treat RAW as a normal editable raster or overwrite it during conversion. Prefer a dedicated RAW processor for development. |

## Frame-preservation behavior

KIM6 distinguishes still images, animated files and multi-page documents. Conversion refuses known frame loss where it cannot preserve the input animation. APNG has a dedicated FFmpeg path; GIF, TIFF, WebP, AVIF, HEIC/HEIF, ICO/CUR, and PDF are treated as potentially multi-frame in relevant conversion checks. Exact support still depends on the coder and action. `stripmeta`, resize, transform, and publication actions validate the expected frame count for their input/output path.

Do not infer “animation supported” from a format name alone. The action’s validation and the local toolchain determine whether a particular file is accepted.

## Color profiles and metadata

ICC profiles are transformed or retained only when a usable profile and output coder are available and the action’s policy requires it. Web export defaults to an actual ICC conversion to sRGB; it does not merely relabel pixels. `--color preserve` attempts to retain an embedded profile when the destination format supports one. Untagged RGB is assumed to be sRGB for web export; untagged CMYK is rejected. Other actions retain their established per-action behavior; this is not a global metadata promise. See [commandconfig.md](commandconfig.md) and [SAFETY.md](SAFETY.md).

## Video formats and encoders

`video` uses FFmpeg with H.264 (`libx264`) or H.265 (`libx265`) at 720p/1080p, CRF 17/23/29, and MP4 or compatible original container. It preserves aspect ratio, avoids unnecessary upscaling and copies compatible audio. An incompatible original container is an error; KIM6 does not silently change it to MP4.

AV1 uses `libsvtav1` when available and falls back to `libaom-av1` only when SVT-AV1 is not advertised. AV1 High and Balanced use distinct encoder settings (CRF 28 and 35 respectively); they are not numeric quality equivalents of H.264/H.265 presets. KIM6 does not fall back from AV1 to another codec.

Audio extraction supports AAC in M4A, MP3, FLAC and PCM WAV, using stream copy for compatible AAC-to-M4A. Audio removal explicitly maps video and compatible non-audio streams without re-encoding video. Video-to-GIF uses a palette-generation/palette-use pipeline and checks loop/timing. Frame extraction/contact sheets use FFmpeg decoding and require relevant filters/fonts where applicable.

Inspect local support without changing system configuration:

```sh
magick -version
magick -list format
ffmpeg -hide_banner -encoders
ffprobe -version
exiftool -ver
```

In `magick -list format`, the read/write permission column is authoritative for that installed ImageMagick build. FFmpeg’s encoder list shows available codec names, but a usable encode still depends on the libraries and container combination. KIM6 performs operation-specific probes and validates outputs rather than treating these listings as universal guarantees.
