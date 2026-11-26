# KIMng Dolphin Menu Actions

KIMng integrates image and video operations into KDE Dolphin.
Its 12 service-menu definitions expose **93 executable static actions** across eight image-related submenu categories and four video-related categories. Five additional desktop action blocks are visual separators, not executable menu actions. Eight menu-entry references point to those five blocks.

The action inventory below is derived directly from the current `.desktop.in` files in `src/`. These are the actual static Dolphin menu labels and dispatcher commands, not historical descriptions.

Saved recipes assigned to Root may also appear dynamically in the Recipes submenu. They are not part of the static service-menu definitions.

## Image menus

### KIMng - Convert/Compress

[View submenu screenshot](images/screenshots/02-convert-compress.png)

| Menu action | Dispatcher command |
|---|---|
| Convert to JPEG | `kim_all convert --preview --format jpg -- %F` |
| Convert to PNG | `kim_all convert --preview --format png -- %F` |
| Convert to WebP | `kim_all convert --preview --format webp -- %F` |
| Convert to AVIF | `kim_all convert --preview --format avif -- %F` |
| Convert to TIFF | `kim_all convert --preview --format tiff -- %F` |
| Convert to GIF | `kim_all convert --preview --format gif -- %F` |
| Convert to HEIC/HEIF | `kim_all convert --preview --format heic -- %F` |
| Convert to PDF | `kim_all convert --preview --format pdf -- %F` |
| Convert to JPEG XL | `kim_all convert --preview --format jxl -- %F` |
| Convert to JPEG 2000 (lossless) | `kim_all convert --preview --format jp2 --jp2-mode lossless -- %F` |
| Convert to JPEG 2000 (lossy) | `kim_all convert --preview --format jp2 --jp2-mode lossy -- %F` |
| Convert to BMP | `kim_all convert --preview --format bmp --bmp5 -- %F` |
| Convert custom… | `kim_all convert --preview --custom-format -- %F` |
| Convert PDF pages to images… | `kim_all pdf-pages -- %F` |
| Extract embedded images from PDF… | `kim_all pdf-extract -- %F` |
| Compress recommended | `kim_all compress --recommended --interactive -- %F` |
| Compress maximum | `kim_all compress --maximum --interactive -- %F` |
| Compress custom… | `kim_all compress --custom -- %F` |

### KIMng - Create/Publish

[View submenu screenshot](images/screenshots/03-create-publish.png)

**Create a gallery…** opens a chooser with two different workflows. **Image gallery** uses the classic gallery creator; **Photo story** opens the three-panel Gallery Publishing editor. It supports five image arrangements, named **Sections**, single-page and multiple-page websites, a local gallery folder or ZIP archive, and mandatory **Review Changes**. See [Gallery Publishing in the User Guide](index.html#gallery-publishing). The `kim_all gallery` command remains available directly and is also invoked by the Image gallery choice.

| Menu action | Dispatcher command |
|---|---|
| Create a gallery… | `kim_all gallery-choose -- %F` |
| Create a collage… | `kim_all collage -- %F` |
| Create a contact sheet… | `kim_all contactsheet -- %F` |
| Create a PDF album… | `kim_all album -- %F` |
| Create a print-layout PDF… | `kim_all print -- %F` |
| Create a video slideshow… | `kim_all slideshow --interactive -- %F` |
| Create an animated image… | `kim_all animate -- %F` |
| Create a multi-page TIFF… | `kim_all tiffjoin -- %F` |
| Send via email… | `kim_all resizeandsend --size full -- %F` |

### KIMng - Location/GPS

[View submenu screenshot](images/screenshots/04-location-gps.png)

| Menu action | Dispatcher command |
|---|---|
| View GPS metadata | `kim_all location-report -- %F` |
| Edit GPS metadata… | `kim_all location-apply -- %F` |
| Reduce exact GPS location… | `kim_all location-reduce -- %F` |
| Remove GPS metadata… | `kim_all stripmeta --mode gps --interactive -- %F` |

### KIMng - Metadata/Organize

[View submenu screenshot](images/screenshots/05-organize-metadata.png)

| Menu action | Dispatcher command |
|---|---|
| Check and correct extensions… | `kim_all checkextensions -- %F` |
| Rename images… | `kim_all rename interactive -- %F` |
| Set dates… | `kim_all capturedate --mode unified --interactive -- %F` |
| Set creator/copyright/usage… | `kim_all copyright --interactive -- %F` |
| Add watermark… | `kim_all overlay -- %F` |
| Strip metadata… | `kim_all stripmeta --interactive -- %F` |
| View metadata | `kim_all metadata-view -- %F` |
| Edit metadata… | `kim_all metadata-edit -- %F` |

View metadata opens the existing read-only Metadata Browser with all selected images in one window. Select exactly two images inside Browser to use its Compare view. Edit metadata opens the existing Metadata Editor with the complete selection; it retains drafts while navigating and only plans changes. Neither action writes image metadata or XMP sidecars.

### KIMng - Recipes

[View submenu screenshot](images/screenshots/06-recipes.png)

| Menu action | Dispatcher command |
|---|---|
| Run a recipe… | `kim_all recipe --choose -- %F` |
| Recipe editor… | `kim_all recipe --editor -- %F` |

### KIMng - Resize/Crop/Rotate

[View submenu screenshot](images/screenshots/07-resize-crop-rotate.png)

| Menu action | Dispatcher command |
|---|---|
| Resize to fit 1600 × 1600 | `kim_all resize --size 1600x1600 -- %F` |
| Resize to fit 1280 × 1280 | `kim_all resize --size 1280x1280 -- %F` |
| Resize to fit 1024 × 1024 | `kim_all resize --size 1024x1024 -- %F` |
| Resize custom… | `kim_all resize --custom -- %F` |
| Crop image… | `kim_all crop -- %F` |
| Auto-rotate using EXIF | `kim_all rotate --preview --exif -- %F` |
| Rotate 90° clockwise | `kim_all rotate --preview --angle 90 -- %F` |
| Rotate 90° counterclockwise | `kim_all rotate --preview --angle 270 -- %F` |
| Rotate 180° | `kim_all rotate --preview --angle 180 -- %F` |
| Rotate custom… | `kim_all rotate --custom -- %F` |
| Flip horizontally | `kim_all flipflop flop -- %F` |
| Flip vertically | `kim_all flipflop flip -- %F` |

### KIMng - Settings/About

[View submenu screenshot](images/screenshots/08-settings-about.png)

| Menu action | Dispatcher command |
|---|---|
| Settings… | `kim_all settings -- %F` |
| About KIMng | `kim_all about -- %F` |
| License | `kim_all license -- %F` |
| User Guide | `kim_all manual -- %F` |

### KIMng - Web Export

[View submenu screenshot](images/screenshots/09-web-export.png)

| Menu action | Dispatcher command |
|---|---|
| JPEG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format jpg -- %F` |
| JPEG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format jpg -- %F` |
| JPEG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format jpg -- %F` |
| PNG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format png -- %F` |
| PNG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format png -- %F` |
| PNG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format png -- %F` |
| WebP · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format webp -- %F` |
| WebP · Medium (800 × 800) | `kim_all webexport --size 800x800 --format webp -- %F` |
| WebP · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format webp -- %F` |
| AVIF · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format avif -- %F` |
| AVIF · Medium (800 × 800) | `kim_all webexport --size 800x800 --format avif -- %F` |
| AVIF · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format avif -- %F` |

## Video menus

KIMng shows video-specific actions when a supported video is selected
in Dolphin. The video menu set comprises three codec conversion
submenus, **AV1**, **H.264**, and **H.265**, plus **Video Utilities**.
The shared **Settings/About** submenu remains available.

![Screenshot needed: 21 video menu overview](images/screenshots/21-video-menu-overview.png)

### Conversion presets

Each video codec submenu provides six MP4 presets: 1080p or 720p
combined with High quality, Balanced, or Smallest file. These are
encoding choices, not promises of particular output sizes.

H.264 generally provides the broadest compatibility. H.265 and AV1
can provide greater compression efficiency, subject to source
content, codec implementation, encoding speed, and playback support.
Available encoders depend on the installed FFmpeg configuration.

![Screenshot needed: 22 video av1 presets](images/screenshots/22-video-av1-presets.png)

### Video Utilities

The six utilities are:

- **Extract audio…**
- **Extract frame at timestamp…**
- **Extract automatic thumbnail**
- **Remove audio (copy video)**
- **Create video contact sheet…**
- **Create animated GIF from video…**

![Screenshot needed: 23 video utilities](images/screenshots/23-video-utilities.png)

The conversion actions and utilities are also documented in the
complete executable action inventory below, including their actual
commands and options.

## File handling and safety

KIMng distinguishes operations that create derivatives from operations that can replace selected originals. Where overwriting is supported, it requires explicit authorization.

Derivative-producing actions must use their applicable output review and filename collision protections. Canceled or blocked operations must not be reported as successful publication.

Recipes never overwrite selected source images.

Image format and codec support are checked at runtime. A visible menu action does not guarantee that every selected input format supports the corresponding transformation.

### Metadata and location privacy

**Edit GPS metadata…** is the main GPS-editing action. Copying coordinates from a reference image and GPX-based geotagging are workflow options rather than separate Dolphin submenu entries.

**Strip metadata…** is the unified metadata-removal action. There is no separate Strip AI metadata menu action.

Removing GPS or AI-related metadata does not guarantee complete anonymity. Other metadata, signed credentials, or visible content may still disclose information.

### Web Export and Recipes

The top-level Web Export submenu provides twelve format-and-size presets (JPEG, PNG, WebP and AVIF at 1600 × 1600, 800 × 800 or 128 × 128 maximum dimensions). JPEG, WebP and AVIF quality settings are independently configurable, with shipped defaults of 95; a screenshot may show the user's saved quality instead. The built-in Web Export recipe is a separate multi-step workflow selected through Recipes: JPEG quality 95, a 1600 × 1600 maximum without upscaling, metadata stripping and output to a `Web` subfolder.

## Related documentation

- [User Guide](index.html)
- [Recipes](RECIPES.md)
- [Supported formats](FORMATS.md)
- [Commands and configuration](commandconfig.md)
- [Installation](../INSTALL.md)

## Authoritative static action inventory

The following inventory is derived from the current KDE service-menu definitions. It records the exact action IDs, labels, and dispatcher commands.

### `kim_compressandresize.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `01Resize1600` | Resize to fit 1600 × 1600 | `kim_all resize --size 1600x1600 -- %F` |
| `02Resize1280` | Resize to fit 1280 × 1280 | `kim_all resize --size 1280x1280 -- %F` |
| `03Resize1024` | Resize to fit 1024 × 1024 | `kim_all resize --size 1024x1024 -- %F` |
| `05ResizeCustom` | Resize custom… | `kim_all resize --custom -- %F` |
| `06Crop` | Crop image… | `kim_all crop -- %F` |
| `14Rotateexif` | Auto-rotate using EXIF | `kim_all rotate --preview --exif -- %F` |
| `10Rotate90` | Rotate 90° clockwise | `kim_all rotate --preview --angle 90 -- %F` |
| `11Rotate270` | Rotate 90° counterclockwise | `kim_all rotate --preview --angle 270 -- %F` |
| `12Rotate180` | Rotate 180° | `kim_all rotate --preview --angle 180 -- %F` |
| `13RotateCustom` | Rotate custom… | `kim_all rotate --custom -- %F` |
| `20FlipHorizontal` | Flip horizontally | `kim_all flipflop flop -- %F` |
| `21FlipVertical` | Flip vertically | `kim_all flipflop flip -- %F` |

### `kim_compressandresizevideo.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `Videohd108017265mp4` | 1080p • High quality • MP4 | `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F` |
| `Videohd108023265mp4` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F` |
| `Videohd108029265mp4` | 1080p • Smallest file • MP4 | `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F` |
| `Videohd72017265mp4` | 720p • High quality • MP4 | `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F` |
| `Videohd72023265mp4` | 720p • Balanced • MP4 | `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F` |
| `Videohd72029265mp4` | 720p • Smallest file • MP4 | `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F` |

### `kim_convertandrotate.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `07ConvertJPG` | Convert to JPEG | `kim_all convert --preview --format jpg -- %F` |
| `10ConvertPNG` | Convert to PNG | `kim_all convert --preview --format png -- %F` |
| `12ConvertWEBP` | Convert to WebP | `kim_all convert --preview --format webp -- %F` |
| `01ConvertAVIF` | Convert to AVIF | `kim_all convert --preview --format avif -- %F` |
| `11ConvertTIFF` | Convert to TIFF | `kim_all convert --preview --format tiff -- %F` |
| `03ConvertGIF` | Convert to GIF | `kim_all convert --preview --format gif -- %F` |
| `04ConvertHEIC` | Convert to HEIC/HEIF | `kim_all convert --preview --format heic -- %F` |
| `09ConvertPDF` | Convert to PDF | `kim_all convert --preview --format pdf -- %F` |
| `08ConvertJXL` | Convert to JPEG XL | `kim_all convert --preview --format jxl -- %F` |
| `05ConvertJP2Lossless` | Convert to JPEG 2000 (lossless) | `kim_all convert --preview --format jp2 --jp2-mode lossless -- %F` |
| `06ConvertJP2Lossy` | Convert to JPEG 2000 (lossy) | `kim_all convert --preview --format jp2 --jp2-mode lossy -- %F` |
| `02ConvertBMP` | Convert to BMP | `kim_all convert --preview --format bmp --bmp5 -- %F` |
| `13ConvertCustom` | Convert custom… | `kim_all convert --preview --custom-format -- %F` |
| `14PDFPages` | Convert PDF pages to images… | `kim_all pdf-pages -- %F` |
| `15PDFExtract` | Extract embedded images from PDF… | `kim_all pdf-extract -- %F` |
| `2001CompressRecommended` | Compress recommended | `kim_all compress --recommended --interactive -- %F` |
| `2102CompressMaximum` | Compress maximum | `kim_all compress --maximum --interactive -- %F` |
| `2203CompressCustom` | Compress custom… | `kim_all compress --custom -- %F` |

### `kim_information.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `01Settings` | Settings… | `kim_all settings -- %F` |
| `02About` | About KIMng | `kim_all about -- %F` |
| `03License` | License | `kim_all license -- %F` |
| `04Manual` | User Guide | `kim_all manual -- %F` |

### `kim_location.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `01Edit` | Edit GPS metadata… | `kim_all location-apply -- %F` |
| `02View` | View GPS metadata | `kim_all location-report -- %F` |
| `03Remove` | Remove GPS metadata… | `kim_all stripmeta --mode gps --interactive -- %F` |
| `04Reduce` | Reduce exact GPS location… | `kim_all location-reduce -- %F` |

### `kim_metadata.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `00ViewMetadata` | View metadata | `kim_all metadata-view -- %F` |
| `01EditMetadata` | Edit metadata… | `kim_all metadata-edit -- %F` |
| `02StripMetadata` | Strip metadata… | `kim_all stripmeta --interactive -- %F` |
| `08SetCopyright` | Set creator/copyright/usage… | `kim_all copyright --interactive -- %F` |
| `04Rename` | Rename images… | `kim_all rename interactive -- %F` |
| `05SetDates` | Set dates… | `kim_all capturedate --mode unified --interactive -- %F` |
| `06CheckExtensions` | Check and correct extensions… | `kim_all checkextensions -- %F` |
| `07Overlay` | Add watermark… | `kim_all overlay -- %F` |

### `kim_publication.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `GalleryChooser` | Create a gallery… | `kim_all gallery-choose -- %F` |
| `Collage` | Create a collage… | `kim_all collage -- %F` |
| `ContactSheet` | Create a contact sheet… | `kim_all contactsheet -- %F` |
| `Album` | Create a PDF album… | `kim_all album -- %F` |
| `Print` | Create a print-layout PDF… | `kim_all print -- %F` |
| `Slideshow` | Create a video slideshow… | `kim_all slideshow --interactive -- %F` |
| `Animation` | Create an animated image… | `kim_all animate -- %F` |
| `TiffJoin` | Create a multi-page TIFF… | `kim_all tiffjoin -- %F` |
| `Emailfull` | Send via email… | `kim_all resizeandsend --size full -- %F` |

### `kim_recipes.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `KIMRecipe0Run` | Run a recipe… | `kim_all recipe --choose -- %F` |
| `KIMRecipe1Editor` | Recipe editor… | `kim_all recipe --editor -- %F` |

### `kim_video_av1.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `01Av1hd1080High` | 1080p • High quality • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F` |
| `02Av1hd1080Balanced` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `03Av1hd1080Smallest` | 1080p • Smallest file • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality smallest --container mp4 -- %F` |
| `04Av1hd720High` | 720p • High quality • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F` |
| `05Av1hd720Balanced` | 720p • Balanced • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F` |
| `06Av1hd720Smallest` | 720p • Smallest file • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality smallest --container mp4 -- %F` |

### `kim_video_h264.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `Videohd108017264mp4` | 1080p • High quality • MP4 | `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F` |
| `Videohd108023264mp4` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F` |
| `Videohd108029264mp4` | 1080p • Smallest file • MP4 | `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F` |
| `Videohd72017264mp4` | 720p • High quality • MP4 | `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F` |
| `Videohd72023264mp4` | 720p • Balanced • MP4 | `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F` |
| `Videohd72029264mp4` | 720p • Smallest file • MP4 | `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F` |

### `kim_videoutilities.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `A01ExtractVideoAudio` | Extract audio… | `kim_all videoaudio --mode extract --format m4a --interactive -- %F` |
| `A02VideoFrameAt` | Extract frame at timestamp… | `kim_all videoframes --mode single --format png --interactive -- %F` |
| `A03VideoThumbnail` | Extract automatic thumbnail | `kim_all videoframes --mode thumbnail --format jpg -- %F` |
| `A04MuteVideo` | Remove audio (copy video) | `kim_all videoaudio --mode mute -- %F` |
| `z01VideoContactSheet` | Create video contact sheet… | `kim_all videoframes --mode contact --format jpg --interactive -- %F` |
| `z02VideoToGif` | Create animated GIF from video… | `kim_all videogif --interactive -- %F` |

### `kim_webemail.desktop.in`

| Action ID | Label | Command |
|---|---|---|
| `0101WebExport` | JPEG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format jpg -- %F` |
| `0102WebExport` | JPEG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format jpg -- %F` |
| `0103WebExport` | JPEG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format jpg -- %F` |
| `0201WebExport` | PNG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format png -- %F` |
| `0202WebExport` | PNG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format png -- %F` |
| `0203WebExport` | PNG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format png -- %F` |
| `0301WebExport` | WebP · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format webp -- %F` |
| `0302WebExport` | WebP · Medium (800 × 800) | `kim_all webexport --size 800x800 --format webp -- %F` |
| `0303WebExport` | WebP · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format webp -- %F` |
| `0401WebExport` | AVIF · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format avif -- %F` |
| `0402WebExport` | AVIF · Medium (800 × 800) | `kim_all webexport --size 800x800 --format avif -- %F` |
| `0403WebExport` | AVIF · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format avif -- %F` |
