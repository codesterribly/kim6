# KIMng Human Acceptance Plan

Generated from 12 current service-menu templates: **91 executable menu actions**.

Regenerate with `python3 qa/acceptance.py inventory`. Do not edit the action list by hand.
Each case has a disposable input copy under `qa/generated/cases/`. Actions must be invoked manually in Dolphin; command execution is not equivalent to GUI acceptance.

## KIMng - Resize/Crop/Rotate (`kim_compressandresize.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_compressandresize.desktop:01Resize1600` | `01Resize1600` | Resize to fit 1600 × 1600 | `kim_all resize --size 1600x1600 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:02Resize1280` | `02Resize1280` | Resize to fit 1280 × 1280 | `kim_all resize --size 1280x1280 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:03Resize1024` | `03Resize1024` | Resize to fit 1024 × 1024 | `kim_all resize --size 1024x1024 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:05ResizeCustom` | `05ResizeCustom` | Resize custom… | `kim_all resize --custom -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:06Crop` | `06Crop` | Crop image… | `kim_all crop -- %F` | wide.jpg | derived |
| `kim_compressandresize.desktop:14Rotateexif` | `14Rotateexif` | Auto-rotate using EXIF | `kim_all rotate --preview --exif -- %F` | orientation-6.jpg | in_place |
| `kim_compressandresize.desktop:10Rotate90` | `10Rotate90` | Rotate 90° clockwise | `kim_all rotate --preview --angle 90 -- %F` | photo.jpg | in_place |
| `kim_compressandresize.desktop:11Rotate270` | `11Rotate270` | Rotate 90° counterclockwise | `kim_all rotate --preview --angle 270 -- %F` | photo.jpg | in_place |
| `kim_compressandresize.desktop:12Rotate180` | `12Rotate180` | Rotate 180° | `kim_all rotate --preview --angle 180 -- %F` | photo.jpg | in_place |
| `kim_compressandresize.desktop:13RotateCustom` | `13RotateCustom` | Rotate custom… | `kim_all rotate --custom -- %F` | photo.jpg | in_place |
| `kim_compressandresize.desktop:20FlipHorizontal` | `20FlipHorizontal` | Flip horizontally | `kim_all flipflop flop -- %F` | photo.jpg | in_place |
| `kim_compressandresize.desktop:21FlipVertical` | `21FlipVertical` | Flip vertically | `kim_all flipflop flip -- %F` | photo.jpg | in_place |

### Resize to fit 1600 × 1600 - `kim_compressandresize.desktop:01Resize1600`

- **Menu path:** KIMng - Resize/Crop/Rotate → Resize to fit 1600 × 1600
- **Dispatcher contract:** `kim_all resize --size 1600x1600 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1600x1600; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1600x1600 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize to fit 1600 × 1600’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize to fit 1280 × 1280 - `kim_compressandresize.desktop:02Resize1280`

- **Menu path:** KIMng - Resize/Crop/Rotate → Resize to fit 1280 × 1280
- **Dispatcher contract:** `kim_all resize --size 1280x1280 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1280x1280; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1280x1280 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize to fit 1280 × 1280’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize to fit 1024 × 1024 - `kim_compressandresize.desktop:03Resize1024`

- **Menu path:** KIMng - Resize/Crop/Rotate → Resize to fit 1024 × 1024
- **Dispatcher contract:** `kim_all resize --size 1024x1024 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1024x1024; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1024x1024 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize to fit 1024 × 1024’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize custom… - `kim_compressandresize.desktop:05ResizeCustom`

- **Menu path:** KIMng - Resize/Crop/Rotate → Resize custom…
- **Dispatcher contract:** `kim_all resize --custom -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom geometry or percentage where requested.; Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Choose a custom size such as 800x600, or choose 50% for the percentage action.
- **Expected:** A correctly sized image tagged `_resized`; check dimensions in the file properties.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize custom…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Crop image… - `kim_compressandresize.desktop:06Crop`

- **Menu path:** KIMng - Resize/Crop/Rotate → Crop image…
- **Dispatcher contract:** `kim_all crop -- %F`
- **Select for the Dolphin context menu:** wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose a crop in the preview and save a separate image in the case folder.
- **Suggested choices:** Choose a centered square crop in the visual preview; keep the source format and save in this case folder.
- **Expected:** A separate cropped image in the case directory matching the preview; source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source preservation are checked. Human: compare crop bounds and dimensions to the preview.
- **Human inspection:** Check that the menu starts the operation named ‘Crop image…’. Check that the result matches the expected behavior below.

### Auto-rotate using EXIF - `kim_compressandresize.desktop:14Rotateexif`

- **Menu path:** KIMng - Resize/Crop/Rotate → Auto-rotate using EXIF
- **Dispatcher contract:** `kim_all rotate --preview --exif -- %F`
- **Select for the Dolphin context menu:** orientation-6.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Choose automatic EXIF orientation correction. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Auto-rotate using EXIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate 90° clockwise - `kim_compressandresize.desktop:10Rotate90`

- **Menu path:** KIMng - Resize/Crop/Rotate → Rotate 90° clockwise
- **Dispatcher contract:** `kim_all rotate --preview --angle 90 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Use the 90 degree rotation. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate 90° clockwise’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate 90° counterclockwise - `kim_compressandresize.desktop:11Rotate270`

- **Menu path:** KIMng - Resize/Crop/Rotate → Rotate 90° counterclockwise
- **Dispatcher contract:** `kim_all rotate --preview --angle 270 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Use the 270 degree rotation. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate 90° counterclockwise’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate 180° - `kim_compressandresize.desktop:12Rotate180`

- **Menu path:** KIMng - Resize/Crop/Rotate → Rotate 180°
- **Dispatcher contract:** `kim_all rotate --preview --angle 180 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Use the 180 degree rotation. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate 180°’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate custom… - `kim_compressandresize.desktop:13RotateCustom`

- **Menu path:** KIMng - Resize/Crop/Rotate → Rotate custom…
- **Dispatcher contract:** `kim_all rotate --custom -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom angle for the custom entry; output policy follows the in-place action dialog.
- **Suggested choices:** Choose a custom angle such as 17 degrees. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate custom…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Flip horizontally - `kim_compressandresize.desktop:20FlipHorizontal`

- **Menu path:** KIMng - Resize/Crop/Rotate → Flip horizontally
- **Dispatcher contract:** `kim_all flipflop flop -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Confirm the horizontal/vertical direction shown in the visible label.
- **Suggested choices:** Use the requested operation: horizontally flop (left and right exchange). Compare the asymmetric colored shapes.
- **Expected:** The selected disposable image is transformed in place: horizontally flop (left and right exchange).
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode and dimensions are valid; compare asymmetric shapes to confirm axis.
- **Human inspection:** Check that the menu starts the operation named ‘Flip horizontally’. Open the result beside its input and use the asymmetric colored shapes to confirm which axis changed.

### Flip vertically - `kim_compressandresize.desktop:21FlipVertical`

- **Menu path:** KIMng - Resize/Crop/Rotate → Flip vertically
- **Dispatcher contract:** `kim_all flipflop flip -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Confirm the horizontal/vertical direction shown in the visible label.
- **Suggested choices:** Use the requested operation: vertically flip (top and bottom exchange). Compare the asymmetric colored shapes.
- **Expected:** The selected disposable image is transformed in place: vertically flip (top and bottom exchange).
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode and dimensions are valid; compare asymmetric shapes to confirm axis.
- **Human inspection:** Check that the menu starts the operation named ‘Flip vertically’. Open the result beside its input and use the asymmetric colored shapes to confirm which axis changed.

## KIMng - Convert Video: H.265 (`kim_compressandresizevideo.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_compressandresizevideo.desktop:Videohd108017265mp4` | `Videohd108017265mp4` | 1080p • High quality • MP4 | `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108023265mp4` | `Videohd108023265mp4` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108029265mp4` | `Videohd108029265mp4` | 1080p • Smallest file • MP4 | `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72017265mp4` | `Videohd72017265mp4` | 720p • High quality • MP4 | `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72023265mp4` | `Videohd72023265mp4` | 720p • Balanced • MP4 | `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72029265mp4` | `Videohd72029265mp4` | 720p • Smallest file • MP4 | `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |

### 1080p • High quality • MP4 - `kim_compressandresizevideo.desktop:Videohd108017265mp4`

- **Menu path:** KIMng - Convert Video: H.265 → 1080p • High quality • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 17, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • High quality • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 1080p • Balanced • MP4 - `kim_compressandresizevideo.desktop:Videohd108023265mp4`

- **Menu path:** KIMng - Convert Video: H.265 → 1080p • Balanced • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 23, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • Balanced • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 1080p • Smallest file • MP4 - `kim_compressandresizevideo.desktop:Videohd108029265mp4`

- **Menu path:** KIMng - Convert Video: H.265 → 1080p • Smallest file • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 29, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • Smallest file • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • High quality • MP4 - `kim_compressandresizevideo.desktop:Videohd72017265mp4`

- **Menu path:** KIMng - Convert Video: H.265 → 720p • High quality • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 17, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • High quality • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • Balanced • MP4 - `kim_compressandresizevideo.desktop:Videohd72023265mp4`

- **Menu path:** KIMng - Convert Video: H.265 → 720p • Balanced • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 23, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • Balanced • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • Smallest file • MP4 - `kim_compressandresizevideo.desktop:Videohd72029265mp4`

- **Menu path:** KIMng - Convert Video: H.265 → 720p • Smallest file • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 29, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • Smallest file • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

## KIMng - Convert/Compress (`kim_convertandrotate.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_convertandrotate.desktop:07ConvertJPG` | `07ConvertJPG` | Convert to JPEG | `kim_all convert --preview --format jpg -- %F` | orientation-6.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:10ConvertPNG` | `10ConvertPNG` | Convert to PNG | `kim_all convert --preview --format png -- %F` | transparent.png | authorized_overwrite |
| `kim_convertandrotate.desktop:12ConvertWEBP` | `12ConvertWEBP` | Convert to WebP | `kim_all convert --preview --format webp -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:01ConvertAVIF` | `01ConvertAVIF` | Convert to AVIF | `kim_all convert --preview --format avif -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:11ConvertTIFF` | `11ConvertTIFF` | Convert to TIFF | `kim_all convert --preview --format tiff -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:03ConvertGIF` | `03ConvertGIF` | Convert to GIF | `kim_all convert --preview --format gif -- %F` | animated.gif | authorized_overwrite |
| `kim_convertandrotate.desktop:04ConvertHEIC` | `04ConvertHEIC` | Convert to HEIC/HEIF | `kim_all convert --preview --format heic -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:09ConvertPDF` | `09ConvertPDF` | Convert to PDF | `kim_all convert --preview --format pdf -- %F` | photo.tif | authorized_overwrite |
| `kim_convertandrotate.desktop:08ConvertJXL` | `08ConvertJXL` | Convert to JPEG XL | `kim_all convert --preview --format jxl -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:05ConvertJP2Lossless` | `05ConvertJP2Lossless` | Convert to JPEG 2000 (lossless) | `kim_all convert --preview --format jp2 --jp2-mode lossless -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:06ConvertJP2Lossy` | `06ConvertJP2Lossy` | Convert to JPEG 2000 (lossy) | `kim_all convert --preview --format jp2 --jp2-mode lossy -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:02ConvertBMP` | `02ConvertBMP` | Convert to BMP | `kim_all convert --preview --format bmp --bmp5 -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:13ConvertCustom` | `13ConvertCustom` | Custom convert… | `kim_all convert --preview --custom-format -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:2001CompressRecommended` | `2001CompressRecommended` | Compress recommended | `kim_all compress --recommended --interactive -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:2102CompressMaximum` | `2102CompressMaximum` | Compress maximum | `kim_all compress --maximum --interactive -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:2203CompressCustom` | `2203CompressCustom` | Compress custom… | `kim_all compress --custom -- %F` | -leading ü [1].jpg | authorized_overwrite |

### Convert to JPEG - `kim_convertandrotate.desktop:07ConvertJPG`

- **Menu path:** KIMng - Convert/Compress → Convert to JPEG
- **Dispatcher contract:** `kim_all convert --preview --format jpg -- %F`
- **Select for the Dolphin context menu:** orientation-6.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to PNG - `kim_convertandrotate.desktop:10ConvertPNG`

- **Menu path:** KIMng - Convert/Compress → Convert to PNG
- **Dispatcher contract:** `kim_all convert --preview --format png -- %F`
- **Select for the Dolphin context menu:** transparent.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets PNG. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable PNG file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to PNG’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to WebP - `kim_convertandrotate.desktop:12ConvertWEBP`

- **Menu path:** KIMng - Convert/Compress → Convert to WebP
- **Dispatcher contract:** `kim_all convert --preview --format webp -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets WEBP. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable WEBP file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to WebP’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to AVIF - `kim_convertandrotate.desktop:01ConvertAVIF`

- **Menu path:** KIMng - Convert/Compress → Convert to AVIF
- **Dispatcher contract:** `kim_all convert --preview --format avif -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets AVIF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable AVIF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to AVIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to TIFF - `kim_convertandrotate.desktop:11ConvertTIFF`

- **Menu path:** KIMng - Convert/Compress → Convert to TIFF
- **Dispatcher contract:** `kim_all convert --preview --format tiff -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets TIFF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable TIFF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to TIFF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to GIF - `kim_convertandrotate.desktop:03ConvertGIF`

- **Menu path:** KIMng - Convert/Compress → Convert to GIF
- **Dispatcher contract:** `kim_all convert --preview --format gif -- %F`
- **Select for the Dolphin context menu:** animated.gif
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets GIF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable GIF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to GIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to HEIC/HEIF - `kim_convertandrotate.desktop:04ConvertHEIC`

- **Menu path:** KIMng - Convert/Compress → Convert to HEIC/HEIF
- **Dispatcher contract:** `kim_all convert --preview --format heic -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets HEIC/HEIF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable HEIC/HEIF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to HEIC/HEIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to PDF - `kim_convertandrotate.desktop:09ConvertPDF`

- **Menu path:** KIMng - Convert/Compress → Convert to PDF
- **Dispatcher contract:** `kim_all convert --preview --format pdf -- %F`
- **Select for the Dolphin context menu:** photo.tif
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets PDF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable PDF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to PDF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to JPEG XL - `kim_convertandrotate.desktop:08ConvertJXL`

- **Menu path:** KIMng - Convert/Compress → Convert to JPEG XL
- **Dispatcher contract:** `kim_all convert --preview --format jxl -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG XL. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG XL file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG XL’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to JPEG 2000 (lossless) - `kim_convertandrotate.desktop:05ConvertJP2Lossless`

- **Menu path:** KIMng - Convert/Compress → Convert to JPEG 2000 (lossless)
- **Dispatcher contract:** `kim_all convert --preview --format jp2 --jp2-mode lossless -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG 2000. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG 2000 file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG 2000 (lossless)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to JPEG 2000 (lossy) - `kim_convertandrotate.desktop:06ConvertJP2Lossy`

- **Menu path:** KIMng - Convert/Compress → Convert to JPEG 2000 (lossy)
- **Dispatcher contract:** `kim_all convert --preview --format jp2 --jp2-mode lossy -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG 2000. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG 2000 file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG 2000 (lossy)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to BMP - `kim_convertandrotate.desktop:02ConvertBMP`

- **Menu path:** KIMng - Convert/Compress → Convert to BMP
- **Dispatcher contract:** `kim_all convert --preview --format bmp --bmp5 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets BMP. The BMP5 preset should produce a BMP5 bitmap. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable BMP file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to BMP’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Custom convert… - `kim_convertandrotate.desktop:13ConvertCustom`

- **Menu path:** KIMng - Convert/Compress → Custom convert…
- **Dispatcher contract:** `kim_all convert --preview --custom-format -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets THE FORMAT YOU CHOOSE. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable THE FORMAT YOU CHOOSE file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Custom convert…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Compress recommended - `kim_convertandrotate.desktop:2001CompressRecommended`

- **Menu path:** KIMng - Convert/Compress → Compress recommended
- **Dispatcher contract:** `kim_all compress --recommended --interactive -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Use the Recommended compression preset; review its format-specific settings and choose create mode.
- **Expected:** A derivative tagged `_compressed` (normally `photo_compressed.jpg` for this JPEG fixture); the selected source remains unchanged.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘Compress recommended’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Compress maximum - `kim_convertandrotate.desktop:2102CompressMaximum`

- **Menu path:** KIMng - Convert/Compress → Compress maximum
- **Dispatcher contract:** `kim_all compress --maximum --interactive -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Use the Maximum compression preset; review its format-specific settings and choose create mode.
- **Expected:** A derivative tagged `_compressed` (normally `photo_compressed.jpg` for this JPEG fixture); the selected source remains unchanged.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘Compress maximum’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Compress custom… - `kim_convertandrotate.desktop:2203CompressCustom`

- **Menu path:** KIMng - Convert/Compress → Compress custom…
- **Dispatcher contract:** `kim_all compress --custom -- %F`
- **Select for the Dolphin context menu:** -leading ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom quality when the menu entry is custom.; Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Enter a JPEG quality from 1 to 100 when prompted; use 50 for this check.
- **Expected:** A JPEG derivative tagged `_compressed`, or the explicitly selected overwrite result.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘Compress custom…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

## KIMng - Settings/About (`kim_information.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_information.desktop:01Settings` | `01Settings` | Settings… | `kim_all settings -- %F` | photo.jpg | none |
| `kim_information.desktop:02About` | `02About` | About KIMng | `kim_all about -- %F` | photo.jpg | none |
| `kim_information.desktop:03License` | `03License` | License | `kim_all license -- %F` | photo.jpg | none |
| `kim_information.desktop:04Manual` | `04Manual` | KIMng User Guide | `kim_all manual -- %F` | photo.jpg | none |

### Settings… - `kim_information.desktop:01Settings`

- **Menu path:** KIMng - Settings/About → Settings…
- **Dispatcher contract:** `kim_all settings -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Inspect Settings tabs, then close without saving; use the isolated QA session.
- **Suggested choices:** Use the isolated QA session, inspect Settings tabs, then close without saving.
- **Expected:** Settings opens; inspect the tabs and close without saving changes.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Human: confirm Settings opens and closes without saving; no media output is expected.
- **Human inspection:** Check that the menu starts the operation named ‘Settings…’. Check that the result matches the expected behavior below.

### About KIMng - `kim_information.desktop:02About`

- **Menu path:** KIMng - Settings/About → About KIMng
- **Dispatcher contract:** `kim_all about -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** KDialog About text opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** kdialog
- **Technical validation:** Dialog is legible and identifies KIMng.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### License - `kim_information.desktop:03License`

- **Menu path:** KIMng - Settings/About → License
- **Dispatcher contract:** `kim_all license -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** Installed LICENSE.md opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Opened document is the installed GPL license.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### KIMng User Guide - `kim_information.desktop:04Manual`

- **Menu path:** KIMng - Settings/About → KIMng User Guide
- **Dispatcher contract:** `kim_all manual -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** Installed docs/index.html and its stylesheet open.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Manual renders and stylesheet loads.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

## KIMng - Location/GPS (`kim_location.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_location.desktop:04Report` | `04Report` | View GPS metadata… | `kim_all location-report -- %F` | metadata.jpg | none |
| `kim_location.desktop:03Apply` | `03Apply` | Edit GPS on images… | `kim_all location-apply -- %F` | metadata.jpg | authorized_overwrite |
| `kim_location.desktop:05Reduce` | `05Reduce` | Reduce exact GPS location… | `kim_all location-reduce -- %F` | metadata.jpg | authorized_overwrite |
| `kim_location.desktop:07StripGPS` | `07StripGPS` | Remove GPS metadata… | `kim_all stripmeta --mode gps --interactive -- %F` | metadata.jpg | authorized_overwrite |

### View GPS metadata… - `kim_location.desktop:04Report`

- **Menu path:** KIMng - Location/GPS → View GPS metadata…
- **Dispatcher contract:** `kim_all location-report -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Inspect the seeded GPS coordinates, then close the read-only inspector.
- **Suggested choices:** Inspect the seeded GPS latitude 42 and longitude 3, then close the read-only inspector.
- **Expected:** The location inspector displays the disposable image's GPS metadata without changing it.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Human: inspect GPS coordinates; source hashes must remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘View GPS metadata…’. Check that the result matches the expected behavior below.

### Edit GPS on images… - `kim_location.desktop:03Apply`

- **Menu path:** KIMng - Location/GPS → Edit GPS on images…
- **Dispatcher contract:** `kim_all location-apply -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose manual coordinates on the disposable metadata image, create mode and the case folder; review the output plan.
- **Suggested choices:** Choose manual coordinates 41, 2 on the disposable metadata image. Choose create mode, keep outputs in this case folder, and review the GPS plan before applying.
- **Expected:** A reviewed derivative with the chosen GPS coordinates, or an explicitly authorized replacement.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source policy are checked. Human: read back the chosen GPS coordinates and unrelated metadata.
- **Human inspection:** Check that the menu starts the operation named ‘Edit GPS on images…’. Check that the result matches the expected behavior below.

### Reduce exact GPS location… - `kim_location.desktop:05Reduce`

- **Menu path:** KIMng - Location/GPS → Reduce exact GPS location…
- **Dispatcher contract:** `kim_all location-reduce -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose reduced coordinate precision and create mode; review the output plan in the case folder.
- **Suggested choices:** Choose reduced GPS precision and create mode; review the planned coordinates before applying. The integer-valued fixture may remain numerically unchanged at coarser precision.
- **Expected:** A reviewed result with reduced GPS precision and unrelated metadata preserved.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source policy are checked. Human: compare GPS precision and unrelated metadata before and after.
- **Human inspection:** Check that the menu starts the operation named ‘Reduce exact GPS location…’. Check that the result matches the expected behavior below.

### Remove GPS metadata… - `kim_location.desktop:07StripGPS`

- **Menu path:** KIMng - Location/GPS → Remove GPS metadata…
- **Dispatcher contract:** `kim_all stripmeta --mode gps --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Suggested choices:** Confirm the requested GPS/location fields only removal when prompted. Choose create mode for this check if offered.
- **Expected:** A result with GPS/location fields only removed; image pixels and unrelated metadata should follow the action's documented policy.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Check that the menu starts the operation named ‘Remove GPS metadata…’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

## KIMng - Organize/Metadata (`kim_metadata.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_metadata.desktop:00CheckExtensions` | `00CheckExtensions` | Check and correct extensions… | `kim_all checkextensions -- %F` | mislabeled.jpg | derived |
| `kim_metadata.desktop:01Rename` | `01Rename` | Rename images… | `kim_all rename interactive -- %F` | dated-photo.jpg, sequence-red.png, -leading ü [1].jpg | rename |
| `kim_metadata.desktop:02SetDates` | `02SetDates` | Set dates… | `kim_all capturedate --mode unified --interactive -- %F` | metadata.jpg | authorized_overwrite |
| `kim_metadata.desktop:04SetCopyright` | `04SetCopyright` | Set creator and copyright… | `kim_all copyright --interactive -- %F` | metadata.jpg | authorized_overwrite |
| `kim_metadata.desktop:04Overlay` | `04Overlay` | Add watermark / overlay… | `kim_all overlay -- %F` | metadata.jpg | derived |
| `kim_metadata.desktop:05StripMetadata` | `05StripMetadata` | Strip metadata | `kim_all stripmeta --interactive -- %F` | metadata.jpg | authorized_overwrite |
| `kim_metadata.desktop:06ViewMetadata` | `06ViewMetadata` | View metadata… | `kim_all metadata-view -- %F` | photo.png | none |
| `kim_metadata.desktop:07EditMetadata` | `07EditMetadata` | Edit metadata… | `kim_all metadata-edit -- %F` | photo.png | none |

### Check and correct extensions… - `kim_metadata.desktop:00CheckExtensions`

- **Menu path:** KIMng - Organize/Metadata → Check and correct extensions…
- **Dispatcher contract:** `kim_all checkextensions -- %F`
- **Select for the Dolphin context menu:** mislabeled.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Inspect the mismatched extension, review the plan and create a correctly named copy in the case folder.
- **Suggested choices:** Inspect mislabeled.jpg (PNG bytes), select it for a correctly named copy, review the plan and create mislabeled.png in this case folder.
- **Expected:** A correctly named PNG copy with identical bytes; the mismatched source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source preservation are checked. Human: confirm the corrected extension and identical bytes.
- **Human inspection:** Check that the menu starts the operation named ‘Check and correct extensions…’. Check that the result matches the expected behavior below.

### Rename images… - `kim_metadata.desktop:01Rename`

- **Menu path:** KIMng - Organize/Metadata → Rename images…
- **Dispatcher contract:** `kim_all rename interactive -- %F`
- **Select for the Dolphin context menu:** dated-photo.jpg, sequence-red.png, -leading ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose naming mode, sequence/base or EXIF date format, destination, and conflict behavior as prompted.
- **Suggested choices:** Choose sequential numbering, use base `acceptance`, start at 1, and select the case folder as the destination.
- **Expected:** The selected files have new names in the chosen case folder; verify all files remain present and ordered.
- **Source behavior:** `rename`. Inputs are case-local disposable copies.
- **Dependencies:** qdbus, kdialog, optional exiftool for EXIF-date mode
- **Technical validation:** Each selected byte hash appears under the expected new name; no unrelated entry is lost.
- **Human inspection:** Check that the menu starts the operation named ‘Rename images…’. Check the resulting names and verify every selected image remains present; compare the names with the selected mode.

### Set dates… - `kim_metadata.desktop:02SetDates`

- **Menu path:** KIMng - Organize/Metadata → Set dates…
- **Dispatcher contract:** `kim_all capturedate --mode unified --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Set a specific capture date and timezone handling, choose create mode and review the preview.
- **Suggested choices:** Set capture date to 2024-03-01 12:00:00, choose UTC and create mode, and review the date preview before applying.
- **Expected:** A reviewed result with the chosen capture date and timezone handling; pixels remain unchanged.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source policy are checked. Human: read back the chosen capture date, timezone and unrelated metadata.
- **Human inspection:** Check that the menu starts the operation named ‘Set dates…’. Check that the result matches the expected behavior below.

### Set creator and copyright… - `kim_metadata.desktop:04SetCopyright`

- **Menu path:** KIMng - Organize/Metadata → Set creator and copyright…
- **Dispatcher contract:** `kim_all copyright --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose creator, notice and/or usage-rights fields; blank fields are left unchanged.
- **Suggested choices:** Enter a short creator and copyright notice, leave usage rights blank, and select only the fields you intend to update. Save in this case folder if asked.
- **Expected:** The chosen rights tags are present; the image pixels and unrelated metadata are unchanged.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Creator/copyright fields read back; unrelated metadata and pixels remain.
- **Human inspection:** Check that the menu starts the operation named ‘Set creator and copyright…’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

### Add watermark / overlay… - `kim_metadata.desktop:04Overlay`

- **Menu path:** KIMng - Organize/Metadata → Add watermark / overlay…
- **Dispatcher contract:** `kim_all overlay -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use a text watermark and save a separate image in the case folder.
- **Suggested choices:** Choose text watermark `KIMng QA`, bottom-right placement and a visible opacity; save a separate result in this case folder.
- **Expected:** A separate watermarked image in the case directory matching the preview; source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source preservation are checked. Human: compare watermark text, placement and opacity to the preview.
- **Human inspection:** Check that the menu starts the operation named ‘Add watermark / overlay…’. Check that the result matches the expected behavior below.

### Strip metadata - `kim_metadata.desktop:05StripMetadata`

- **Menu path:** KIMng - Organize/Metadata → Strip metadata
- **Dispatcher contract:** `kim_all stripmeta --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Suggested choices:** Confirm the requested all metadata removal when prompted. Choose create mode for this check if offered.
- **Expected:** A result with all metadata removed; image pixels and unrelated metadata should follow the action's documented policy.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Check that the menu starts the operation named ‘Strip metadata’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

### View metadata… - `kim_metadata.desktop:06ViewMetadata`

- **Menu path:** KIMng - Organize/Metadata → View metadata…
- **Dispatcher contract:** `kim_all metadata-view -- %F`
- **Select for the Dolphin context menu:** photo.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Inspect metadata and alternate representations, then close without writing.
- **Suggested choices:** Browse metadata and provenance without writing.
- **Expected:** Open the read-only Metadata Browser and inspect the source without changing it.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, exiftool
- **Technical validation:** Read-only inspection must preserve source bytes and timestamps; inspect metadata provenance.
- **Human inspection:** Check that the menu starts the operation named ‘View metadata…’. Confirm the source bytes and filesystem timestamps remain unchanged.

### Edit metadata… - `kim_metadata.desktop:07EditMetadata`

- **Menu path:** KIMng - Organize/Metadata → Edit metadata…
- **Dispatcher contract:** `kim_all metadata-edit -- %F`
- **Select for the Dolphin context menu:** photo.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Propose a metadata change, then cancel. No writes are permitted in Phase 1.
- **Suggested choices:** Inspect a change proposal and cancel; no write is permitted.
- **Expected:** Inspect a proposal in the read-only Metadata Editor, then cancel without writing.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, exiftool
- **Technical validation:** Phase 1 is read-only. Verify proposals without writing and preserve source bytes and timestamps.
- **Human inspection:** Check that the menu starts the operation named ‘Edit metadata…’. Confirm the source bytes and filesystem timestamps remain unchanged.

## KIMng - Create/Publish (`kim_publication.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_publication.desktop:Gallery` | `Gallery` | Create an HTML gallery… | `kim_all gallery -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Collage` | `Collage` | Create a collage… | `kim_all collage -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:ContactSheet` | `ContactSheet` | Create a contact sheet… | `kim_all contactsheet -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Album` | `Album` | Create a PDF album… | `kim_all album -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Print` | `Print` | Create a print-layout PDF… | `kim_all print -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Slideshow` | `Slideshow` | Create a video slideshow… | `kim_all slideshow --interactive -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Animation` | `Animation` | Create an animated image… | `kim_all animate -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:TiffJoin` | `TiffJoin` | Create a multi-page TIFF… | `kim_all tiffjoin -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Emailfull` | `Emailfull` | Send via email… | `kim_all resizeandsend --size full -- %F` | photo.jpg, wide.jpg | derived |

### Create an HTML gallery… - `kim_publication.desktop:Gallery`

- **Menu path:** KIMng - Create/Publish → Create an HTML gallery…
- **Dispatcher contract:** `kim_all gallery -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Enter gallery title/author and layout/output options.
- **Suggested choices:** Enter title `KIMng acceptance`, author `QA`, and 3 columns; choose this case folder for the gallery output if asked.
- **Expected:** A gallery directory with an index, full-size images and thumbnails.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional xdg-open
- **Technical validation:** index.html and all relative image/thumbnail references exist.
- **Human inspection:** Check that the menu starts the operation named ‘Create an HTML gallery…’. Open the gallery index in a browser, click a thumbnail and check the title, author and columns.

### Create a collage… - `kim_publication.desktop:Collage`

- **Menu path:** KIMng - Create/Publish → Create a collage…
- **Dispatcher contract:** `kim_all collage -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose canvas/image size, layout, background, border, spacing/overlap and rotation/shadow options.
- **Suggested choices:** Use the defaults shown: 400x400 image size, 5x4 grid, 15% overlap and grey background; save in this case folder.
- **Expected:** A PNG collage containing all three colored source images.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Image decodes and selected tile ordering/layout is visible.
- **Human inspection:** Check that the menu starts the operation named ‘Create a collage…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Create a contact sheet… - `kim_publication.desktop:ContactSheet`

- **Menu path:** KIMng - Create/Publish → Create a contact sheet…
- **Dispatcher contract:** `kim_all contactsheet -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose page size/orientation, grid, labels, image fit, background, resolution and title.
- **Suggested choices:** Choose A4, a 3x3 grid and filename labels; save the PDF in this case folder.
- **Expected:** A readable PDF contact sheet showing all selected images and their filename labels; compare order, grid and page size visually.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, PDF delegate
- **Technical validation:** Automated: pdfinfo reports readable pages and correct physical size. Human: inspect image order, number/filename labels, grid and pagination.
- **Human inspection:** Check that the menu starts the operation named ‘Create a contact sheet…’. Check that the result matches the expected behavior below.

### Create a PDF album… - `kim_publication.desktop:Album`

- **Menu path:** KIMng - Create/Publish → Create a PDF album…
- **Dispatcher contract:** `kim_all album -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose an album layout and output filename; this action does not prompt for a title.
- **Suggested choices:** Choose `2x2 landscape album` (the default), then accept the suggested output name in this case folder.
- **Expected:** A multi-page PDF album with the three selected images in order.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, PDF delegate
- **Technical validation:** Automated: pdfinfo can read the PDF and reports a positive page count and physical page size. Human: compare page count, image order and layout to the selected options.
- **Human inspection:** Check that the menu starts the operation named ‘Create a PDF album…’. Open the PDF and check page orientation, image order and layout; automated page counts do not judge layout quality.

### Create a print-layout PDF… - `kim_publication.desktop:Print`

- **Menu path:** KIMng - Create/Publish → Create a print-layout PDF…
- **Dispatcher contract:** `kim_all print -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose one of the supported print layouts and page settings.
- **Suggested choices:** Choose `11.5x15 cm: 1x2 images, portrait` (the default), then save the PDF in this case folder.
- **Expected:** A print-layout PDF with portrait physical pages and the selected images.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, PDF delegate
- **Technical validation:** Automated: pdfinfo can read the PDF and reports a positive page count and physical page size. Human: compare page orientation and print layout to the chosen options.
- **Human inspection:** Check that the menu starts the operation named ‘Create a print-layout PDF…’. Open the PDF and check page orientation, image order and layout; automated page counts do not judge layout quality.

### Create a video slideshow… - `kim_publication.desktop:Slideshow`

- **Menu path:** KIMng - Create/Publish → Create a video slideshow…
- **Dispatcher contract:** `kim_all slideshow --interactive -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose slide duration, frame size/rate, background and ordering options.
- **Suggested choices:** Use 3 seconds per photo, 1280x720, 25 fps, black background and the natural filename ordering; save as `slideshow.mp4` in this case folder.
- **Expected:** A silent H.264 MP4 showing red, green, then blue slides, each for about 3 seconds.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick, identify, libx264, qdbus, kdialog
- **Technical validation:** Automated: ffprobe confirms H.264 MP4, observed dimensions, selected frame rate, approximate duration, frame count when reported, no audio, and full decode. Human: compare image order and dimensions to the interactive choices.
- **Human inspection:** Check that the menu starts the operation named ‘Create a video slideshow…’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Create an animated image… - `kim_publication.desktop:Animation`

- **Menu path:** KIMng - Create/Publish → Create an animated image…
- **Dispatcher contract:** `kim_all animate -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose frame delay and animation settings.
- **Suggested choices:** Use a 100-centisecond frame delay and loop count 0 (infinite); save the GIF in this case folder.
- **Expected:** An animated GIF showing red, green, then blue frames and looping continuously.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Automated: GIF fully decodes and frame count matches selected input frame count. Human: inspect frame order, delay and loop behavior.
- **Human inspection:** Check that the menu starts the operation named ‘Create an animated image…’. Open the GIF in an animation-capable viewer and check red, green, blue order, delay and looping.

### Create a multi-page TIFF… - `kim_publication.desktop:TiffJoin`

- **Menu path:** KIMng - Create/Publish → Create a multi-page TIFF…
- **Dispatcher contract:** `kim_all tiffjoin -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose the output location/name; selected order is used.
- **Suggested choices:** Accept the suggested TIFF output name and choose this case folder if a destination is requested.
- **Expected:** A multi-page TIFF whose pages follow the selected red, green, blue order.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Automated: TIFF fully decodes and page count matches selected input frame count. Human: inspect page order.
- **Human inspection:** Check that the menu starts the operation named ‘Create a multi-page TIFF…’. Open the TIFF as pages and check that red, green, then blue appear in that order.

### Send via email… - `kim_publication.desktop:Emailfull`

- **Menu path:** KIMng - Create/Publish → Send via email…
- **Dispatcher contract:** `kim_all resizeandsend --size full -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Suggested choices:** Use the full mail preset. Inspect the draft's attachment list, then close the draft without sending.
- **Expected:** A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Send via email…’. Check that the draft contains only the expected prepared images and do not send it.

## KIMng - Recipes (`kim_recipes.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_recipes.desktop:KIMRecipe0Run` | `KIMRecipe0Run` | Choose saved recipe… | `kim_all recipe --choose -- %F` | orientation-6.jpg | derived |
| `kim_recipes.desktop:KIMRecipe1Editor` | `KIMRecipe1Editor` | Recipe editor… | `kim_all recipe --editor -- %F` | photo.jpg | none |

### Choose saved recipe… - `kim_recipes.desktop:KIMRecipe0Run`

- **Menu path:** KIMng - Recipes → Choose saved recipe…
- **Dispatcher contract:** `kim_all recipe --choose -- %F`
- **Select for the Dolphin context menu:** orientation-6.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose the built-in Web Export recipe and review its plan; for the editor, inspect and close without saving.
- **Suggested choices:** Choose Built-In → Web Export; review the output preview and run only on this case's disposable image. Keep the Web destination inside this case folder.
- **Expected:** The built-in Web Export recipe creates a JPEG in this case's Web subfolder; source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source preservation are checked for recipe outputs. Human: inspect the chosen recipe and its output preview, or confirm the editor opens and closes without saving.
- **Human inspection:** Check that the menu starts the operation named ‘Choose saved recipe…’. Check that the result matches the expected behavior below.

### Recipe editor… - `kim_recipes.desktop:KIMRecipe1Editor`

- **Menu path:** KIMng - Recipes → Recipe editor…
- **Dispatcher contract:** `kim_all recipe --editor -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose the built-in Web Export recipe and review its plan; for the editor, inspect and close without saving.
- **Suggested choices:** Inspect the built-in Web Export recipe in Recipe Editor, then close without saving or running.
- **Expected:** Recipe Editor opens; inspect the built-in recipe and close without saving or running.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** python3, PySide6, magick, exiftool
- **Technical validation:** Automated: decode and source preservation are checked for recipe outputs. Human: inspect the chosen recipe and its output preview, or confirm the editor opens and closes without saving.
- **Human inspection:** Check that the menu starts the operation named ‘Recipe editor…’. Check that the result matches the expected behavior below.

## KIMng - Convert Video: AV1 (`kim_video_av1.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_video_av1.desktop:01Av1hd1080High` | `01Av1hd1080High` | 1080p • High quality • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_av1.desktop:02Av1hd1080Balanced` | `02Av1hd1080Balanced` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_av1.desktop:03Av1hd1080Smallest` | `03Av1hd1080Smallest` | 1080p • Smallest file • MP4 | `kim_all video --size hd1080 --codec av1 --av1-quality smallest --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_av1.desktop:04Av1hd720High` | `04Av1hd720High` | 720p • High quality • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_av1.desktop:05Av1hd720Balanced` | `05Av1hd720Balanced` | 720p • Balanced • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F` | video-silent.mp4 | authorized_overwrite |
| `kim_video_av1.desktop:06Av1hd720Smallest` | `06Av1hd720Smallest` | 720p • Smallest file • MP4 | `kim_all video --size hd720 --codec av1 --av1-quality smallest --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |

### 1080p • High quality • MP4 - `kim_video_av1.desktop:01Av1hd1080High`

- **Menu path:** KIMng - Convert Video: AV1 → 1080p • High quality • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 high quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 high quality; output size hd1080; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • High quality • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 1080p • Balanced • MP4 - `kim_video_av1.desktop:02Av1hd1080Balanced`

- **Menu path:** KIMng - Convert Video: AV1 → 1080p • Balanced • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 balanced quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 balanced quality; output size hd1080; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • Balanced • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 1080p • Smallest file • MP4 - `kim_video_av1.desktop:03Av1hd1080Smallest`

- **Menu path:** KIMng - Convert Video: AV1 → 1080p • Smallest file • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality smallest --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 smallest quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 smallest quality; output size hd1080; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • Smallest file • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • High quality • MP4 - `kim_video_av1.desktop:04Av1hd720High`

- **Menu path:** KIMng - Convert Video: AV1 → 720p • High quality • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 high quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 high quality; output size hd720; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • High quality • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • Balanced • MP4 - `kim_video_av1.desktop:05Av1hd720Balanced`

- **Menu path:** KIMng - Convert Video: AV1 → 720p • Balanced • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-silent.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 balanced quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 balanced quality; output size hd720; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • Balanced • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • Smallest file • MP4 - `kim_video_av1.desktop:06Av1hd720Smallest`

- **Menu path:** KIMng - Convert Video: AV1 → 720p • Smallest file • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --codec av1 --av1-quality smallest --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 smallest quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 smallest quality; output size hd720; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • Smallest file • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

## KIMng - Convert Video: H.264 (`kim_video_h264.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_video_h264.desktop:Videohd108017264mp4` | `Videohd108017264mp4` | 1080p • High quality • MP4 | `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_h264.desktop:Videohd108023264mp4` | `Videohd108023264mp4` | 1080p • Balanced • MP4 | `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_h264.desktop:Videohd108029264mp4` | `Videohd108029264mp4` | 1080p • Smallest file • MP4 | `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_h264.desktop:Videohd72017264mp4` | `Videohd72017264mp4` | 720p • High quality • MP4 | `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F` | video-silent.mp4 | authorized_overwrite |
| `kim_video_h264.desktop:Videohd72023264mp4` | `Videohd72023264mp4` | 720p • Balanced • MP4 | `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_video_h264.desktop:Videohd72029264mp4` | `Videohd72029264mp4` | 720p • Smallest file • MP4 | `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |

### 1080p • High quality • MP4 - `kim_video_h264.desktop:Videohd108017264mp4`

- **Menu path:** KIMng - Convert Video: H.264 → 1080p • High quality • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 17, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • High quality • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 1080p • Balanced • MP4 - `kim_video_h264.desktop:Videohd108023264mp4`

- **Menu path:** KIMng - Convert Video: H.264 → 1080p • Balanced • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 23, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • Balanced • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 1080p • Smallest file • MP4 - `kim_video_h264.desktop:Videohd108029264mp4`

- **Menu path:** KIMng - Convert Video: H.264 → 1080p • Smallest file • MP4
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 29, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘1080p • Smallest file • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • High quality • MP4 - `kim_video_h264.desktop:Videohd72017264mp4`

- **Menu path:** KIMng - Convert Video: H.264 → 720p • High quality • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-silent.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 17, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • High quality • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • Balanced • MP4 - `kim_video_h264.desktop:Videohd72023264mp4`

- **Menu path:** KIMng - Convert Video: H.264 → 720p • Balanced • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 23, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • Balanced • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### 720p • Smallest file • MP4 - `kim_video_h264.desktop:Videohd72029264mp4`

- **Menu path:** KIMng - Convert Video: H.264 → 720p • Smallest file • MP4
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 29, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘720p • Smallest file • MP4’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

## KIMng - Video Utilities (`kim_videoutilities.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_videoutilities.desktop:A01ExtractVideoAudio` | `A01ExtractVideoAudio` | Extract audio… | `kim_all videoaudio --mode extract --format m4a --interactive -- %F` | video-multiaudio.mkv | derived |
| `kim_videoutilities.desktop:A02VideoFrameAt` | `A02VideoFrameAt` | Extract frame at timestamp… | `kim_all videoframes --mode single --format png --interactive -- %F` | video-audio.mp4 | derived |
| `kim_videoutilities.desktop:A03VideoThumbnail` | `A03VideoThumbnail` | Extract automatic thumbnail | `kim_all videoframes --mode thumbnail --format jpg -- %F` | video-audio.mp4 | derived |
| `kim_videoutilities.desktop:A04MuteVideo` | `A04MuteVideo` | Remove audio (copy video) | `kim_all videoaudio --mode mute -- %F` | video-multiaudio.mkv | derived |
| `kim_videoutilities.desktop:z01VideoContactSheet` | `z01VideoContactSheet` | Create video contact sheet… | `kim_all videoframes --mode contact --format jpg --interactive -- %F` | video-audio.mp4 | derived |
| `kim_videoutilities.desktop:z02VideoToGif` | `z02VideoToGif` | Create animated GIF from video… | `kim_all videogif --interactive -- %F` | video-audio.mp4 | derived |

### Extract audio… - `kim_videoutilities.desktop:A01ExtractVideoAudio`

- **Menu path:** KIMng - Video Utilities → Extract audio…
- **Dispatcher contract:** `kim_all videoaudio --mode extract --format m4a --interactive -- %F`
- **Select for the Dolphin context menu:** video-multiaudio.mkv
- **Files passed to dispatcher:** yes
- **Interactive choices:** Audio format only for the extract entry; mute has no format dialog.
- **Suggested choices:** Choose M4A/AAC when asked and accept the suggested output name.
- **Expected:** An audio-only M4A file; inspect the draft/file and confirm no video stream is present.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, audio encoder as requested
- **Technical validation:** ffprobe confirms audio codec/container and stream count, or confirms no audio after mute; full decode and approximate duration are checked.
- **Human inspection:** Check that the menu starts the operation named ‘Extract audio…’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Extract frame at timestamp… - `kim_videoutilities.desktop:A02VideoFrameAt`

- **Menu path:** KIMng - Video Utilities → Extract frame at timestamp…
- **Dispatcher contract:** `kim_all videoframes --mode single --format png --interactive -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Timestamp or contact-sheet grid only for interactive entries; format is fixed by the menu preset.
- **Suggested choices:** Enter timestamp 00:00:01.000 and keep PNG format.
- **Expected:** One PNG frame taken at the requested timestamp.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick for contact sheets, qdbus, kdialog
- **Technical validation:** Automated: output image fully decodes and observed dimensions/frame count are reported. Human: check requested timestamp and contact-sheet labels.
- **Human inspection:** Check that the menu starts the operation named ‘Extract frame at timestamp…’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Extract automatic thumbnail - `kim_videoutilities.desktop:A03VideoThumbnail`

- **Menu path:** KIMng - Video Utilities → Extract automatic thumbnail
- **Dispatcher contract:** `kim_all videoframes --mode thumbnail --format jpg -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Timestamp or contact-sheet grid only for interactive entries; format is fixed by the menu preset.
- **Suggested choices:** Accept the automatic thumbnail choice and JPG format.
- **Expected:** One representative video thumbnail; sampling uses the action's documented midpoint rule.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick for contact sheets, qdbus, kdialog
- **Technical validation:** Automated: output image fully decodes and observed dimensions/frame count are reported. Human: check requested timestamp and contact-sheet labels.
- **Human inspection:** Check that the menu starts the operation named ‘Extract automatic thumbnail’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Remove audio (copy video) - `kim_videoutilities.desktop:A04MuteVideo`

- **Menu path:** KIMng - Video Utilities → Remove audio (copy video)
- **Dispatcher contract:** `kim_all videoaudio --mode mute -- %F`
- **Select for the Dolphin context menu:** video-multiaudio.mkv
- **Files passed to dispatcher:** yes
- **Interactive choices:** Audio format only for the extract entry; mute has no format dialog.
- **Suggested choices:** Choose the suggested output name. Do not select an audio format; this operation copies video streams and removes audio.
- **Expected:** A new silent video with the video stream copied without re-encoding.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, audio encoder as requested
- **Technical validation:** ffprobe confirms audio codec/container and stream count, or confirms no audio after mute; full decode and approximate duration are checked.
- **Human inspection:** Check that the menu starts the operation named ‘Remove audio (copy video)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Create video contact sheet… - `kim_videoutilities.desktop:z01VideoContactSheet`

- **Menu path:** KIMng - Video Utilities → Create video contact sheet…
- **Dispatcher contract:** `kim_all videoframes --mode contact --format jpg --interactive -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Timestamp or contact-sheet grid only for interactive entries; format is fixed by the menu preset.
- **Suggested choices:** Choose a 3x3 grid, PNG format, and accept the suggested output name.
- **Expected:** One labeled contact sheet with sampled frames and timestamps.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick for contact sheets, qdbus, kdialog
- **Technical validation:** Automated: output image fully decodes and observed dimensions/frame count are reported. Human: check requested timestamp and contact-sheet labels.
- **Human inspection:** Check that the menu starts the operation named ‘Create video contact sheet…’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Create animated GIF from video… - `kim_videoutilities.desktop:z02VideoToGif`

- **Menu path:** KIMng - Video Utilities → Create animated GIF from video…
- **Dispatcher contract:** `kim_all videogif --interactive -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose interval, frame rate, width and loop behavior.
- **Suggested choices:** Use start 00:00:00, duration 2 seconds, 10 fps, width 320, and infinite loop.
- **Expected:** A small animated GIF of the requested video segment.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog
- **Technical validation:** Automated: GIF fully decodes, has at least two frames, and observed dimensions are reported. Human: inspect timing and loop behavior.
- **Human inspection:** Check that the menu starts the operation named ‘Create animated GIF from video…’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

## KIMng - Web Export (`kim_webemail.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_webemail.desktop:0101WebExport` | `0101WebExport` | JPEG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format jpg -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0102WebExport` | `0102WebExport` | JPEG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format jpg -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0103WebExport` | `0103WebExport` | JPEG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format jpg -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0201WebExport` | `0201WebExport` | PNG · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format png -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0202WebExport` | `0202WebExport` | PNG · Medium (800 × 800) | `kim_all webexport --size 800x800 --format png -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0203WebExport` | `0203WebExport` | PNG · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format png -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0301WebExport` | `0301WebExport` | WebP · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format webp -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0302WebExport` | `0302WebExport` | WebP · Medium (800 × 800) | `kim_all webexport --size 800x800 --format webp -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0303WebExport` | `0303WebExport` | WebP · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format webp -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0401WebExport` | `0401WebExport` | AVIF · Large (1600 × 1600) | `kim_all webexport --size 1600x1600 --format avif -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0402WebExport` | `0402WebExport` | AVIF · Medium (800 × 800) | `kim_all webexport --size 800x800 --format avif -- %F` | profile-wide.jpg | derived |
| `kim_webemail.desktop:0403WebExport` | `0403WebExport` | AVIF · Thumbnail (128 × 128) | `kim_all webexport --size 128x128 --format avif -- %F` | profile-wide.jpg | derived |

### JPEG · Large (1600 × 1600) - `kim_webemail.desktop:0101WebExport`

- **Menu path:** KIMng - Web Export → JPEG · Large (1600 × 1600)
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --format jpg -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 1600x1600 size and quality 75 preset; select this case folder as the export destination. Format: jpg. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG · Large (1600 × 1600)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### JPEG · Medium (800 × 800) - `kim_webemail.desktop:0102WebExport`

- **Menu path:** KIMng - Web Export → JPEG · Medium (800 × 800)
- **Dispatcher contract:** `kim_all webexport --size 800x800 --format jpg -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 800x800 size and quality 75 preset; select this case folder as the export destination. Format: jpg. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG · Medium (800 × 800)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### JPEG · Thumbnail (128 × 128) - `kim_webemail.desktop:0103WebExport`

- **Menu path:** KIMng - Web Export → JPEG · Thumbnail (128 × 128)
- **Dispatcher contract:** `kim_all webexport --size 128x128 --format jpg -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 128x128 size and quality 75 preset; select this case folder as the export destination. Format: jpg. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG · Thumbnail (128 × 128)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### PNG · Large (1600 × 1600) - `kim_webemail.desktop:0201WebExport`

- **Menu path:** KIMng - Web Export → PNG · Large (1600 × 1600)
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --format png -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 1600x1600 size and quality 75 preset; select this case folder as the export destination. Format: png. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘PNG · Large (1600 × 1600)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### PNG · Medium (800 × 800) - `kim_webemail.desktop:0202WebExport`

- **Menu path:** KIMng - Web Export → PNG · Medium (800 × 800)
- **Dispatcher contract:** `kim_all webexport --size 800x800 --format png -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 800x800 size and quality 75 preset; select this case folder as the export destination. Format: png. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘PNG · Medium (800 × 800)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### PNG · Thumbnail (128 × 128) - `kim_webemail.desktop:0203WebExport`

- **Menu path:** KIMng - Web Export → PNG · Thumbnail (128 × 128)
- **Dispatcher contract:** `kim_all webexport --size 128x128 --format png -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 128x128 size and quality 75 preset; select this case folder as the export destination. Format: png. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘PNG · Thumbnail (128 × 128)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### WebP · Large (1600 × 1600) - `kim_webemail.desktop:0301WebExport`

- **Menu path:** KIMng - Web Export → WebP · Large (1600 × 1600)
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --format webp -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 1600x1600 size and quality 75 preset; select this case folder as the export destination. Format: webp. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘WebP · Large (1600 × 1600)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### WebP · Medium (800 × 800) - `kim_webemail.desktop:0302WebExport`

- **Menu path:** KIMng - Web Export → WebP · Medium (800 × 800)
- **Dispatcher contract:** `kim_all webexport --size 800x800 --format webp -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 800x800 size and quality 75 preset; select this case folder as the export destination. Format: webp. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘WebP · Medium (800 × 800)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### WebP · Thumbnail (128 × 128) - `kim_webemail.desktop:0303WebExport`

- **Menu path:** KIMng - Web Export → WebP · Thumbnail (128 × 128)
- **Dispatcher contract:** `kim_all webexport --size 128x128 --format webp -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 128x128 size and quality 75 preset; select this case folder as the export destination. Format: webp. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘WebP · Thumbnail (128 × 128)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### AVIF · Large (1600 × 1600) - `kim_webemail.desktop:0401WebExport`

- **Menu path:** KIMng - Web Export → AVIF · Large (1600 × 1600)
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --format avif -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 1600x1600 size and quality 75 preset; select this case folder as the export destination. Format: avif. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘AVIF · Large (1600 × 1600)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### AVIF · Medium (800 × 800) - `kim_webemail.desktop:0402WebExport`

- **Menu path:** KIMng - Web Export → AVIF · Medium (800 × 800)
- **Dispatcher contract:** `kim_all webexport --size 800x800 --format avif -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 800x800 size and quality 75 preset; select this case folder as the export destination. Format: avif. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘AVIF · Medium (800 × 800)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### AVIF · Thumbnail (128 × 128) - `kim_webemail.desktop:0403WebExport`

- **Menu path:** KIMng - Web Export → AVIF · Thumbnail (128 × 128)
- **Dispatcher contract:** `kim_all webexport --size 128x128 --format avif -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 128x128 size and quality 75 preset; select this case folder as the export destination. Format: avif. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘AVIF · Thumbnail (128 × 128)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

## Status meanings

The CLI result log separates **GUI verified**, **CLI verified**, **GUI blocked by KDE**, and **Not tested**. Only a person invoking a menu in Dolphin can record GUI verification. `validate` performs technical checks only.
