# KIM6 Human Acceptance Plan

Generated from the five current service-menu templates: **107 menu actions**.

Regenerate with `python3 qa/acceptance.py inventory`. Do not edit the action list by hand.
Each case has a disposable input copy under `qa/generated/cases/`. Actions must be invoked manually in Dolphin; command execution is not equivalent to GUI acceptance.

## JPEG compression (`kim_compress.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_compress.desktop:Compress10` | `Compress10` | JPEG quality: 10% | `kim_all compress --quality 10 -- %F` | photo.jpg | authorized_overwrite |
| `kim_compress.desktop:Compress30` | `Compress30` | JPEG quality: 30% | `kim_all compress --quality 30 -- %F` | photo.jpg | authorized_overwrite |
| `kim_compress.desktop:Compress50` | `Compress50` | JPEG quality: 50% | `kim_all compress --quality 50 -- %F` | photo.jpg | authorized_overwrite |
| `kim_compress.desktop:Compress70` | `Compress70` | JPEG quality: 70% | `kim_all compress --quality 70 -- %F` | photo.jpg | authorized_overwrite |
| `kim_compress.desktop:Compress90` | `Compress90` | JPEG quality: 90% | `kim_all compress --quality 90 -- %F` | photo.jpg | authorized_overwrite |
| `kim_compress.desktop:CompressCustom` | `CompressCustom` | Compress at custom quality… | `kim_all compress --custom -- %F` | -leading ü [1].jpg | authorized_overwrite |

### JPEG quality: 10% — `kim_compress.desktop:Compress10`

- **Menu path:** KIM6 → JPEG compression → JPEG quality: 10%
- **Dispatcher contract:** `kim_all compress --quality 10 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated JPEG beside the selected image, tagged _compressed (or configured prefix), collision numbered.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Confirm the dialog/action title matches: JPEG quality: 10% Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### JPEG quality: 30% — `kim_compress.desktop:Compress30`

- **Menu path:** KIM6 → JPEG compression → JPEG quality: 30%
- **Dispatcher contract:** `kim_all compress --quality 30 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated JPEG beside the selected image, tagged _compressed (or configured prefix), collision numbered.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Confirm the dialog/action title matches: JPEG quality: 30% Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### JPEG quality: 50% — `kim_compress.desktop:Compress50`

- **Menu path:** KIM6 → JPEG compression → JPEG quality: 50%
- **Dispatcher contract:** `kim_all compress --quality 50 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated JPEG beside the selected image, tagged _compressed (or configured prefix), collision numbered.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Confirm the dialog/action title matches: JPEG quality: 50% Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### JPEG quality: 70% — `kim_compress.desktop:Compress70`

- **Menu path:** KIM6 → JPEG compression → JPEG quality: 70%
- **Dispatcher contract:** `kim_all compress --quality 70 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated JPEG beside the selected image, tagged _compressed (or configured prefix), collision numbered.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Confirm the dialog/action title matches: JPEG quality: 70% Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### JPEG quality: 90% — `kim_compress.desktop:Compress90`

- **Menu path:** KIM6 → JPEG compression → JPEG quality: 90%
- **Dispatcher contract:** `kim_all compress --quality 90 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated JPEG beside the selected image, tagged _compressed (or configured prefix), collision numbered.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Confirm the dialog/action title matches: JPEG quality: 90% Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Compress at custom quality… — `kim_compress.desktop:CompressCustom`

- **Menu path:** KIM6 → JPEG compression → Compress at custom quality…
- **Dispatcher contract:** `kim_all compress --custom -- %F`
- **Select for the Dolphin context menu:** -leading ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom quality when the menu entry is custom.; Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated JPEG beside the selected image, tagged _compressed (or configured prefix), collision numbered.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Confirm the dialog/action title matches: Compress at custom quality… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

## Resize, web export and email (`kim_compressandresize.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_compressandresize.desktop:Resize300` | `Resize300` | Resize (300x300 pixels) | `kim_all resize --size 300x300 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize600` | `Resize600` | Resize (600x600 pixels) | `kim_all resize --size 600x600 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize800` | `Resize800` | Resize (800x800 pixels) | `kim_all resize --size 800x800 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize1024` | `Resize1024` | Resize (1024x1024 pixels) | `kim_all resize --size 1024x1024 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize1280` | `Resize1280` | Resize (1280x1280 pixels) | `kim_all resize --size 1280x1280 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize1400` | `Resize1400` | Resize (1400x1400 pixels) | `kim_all resize --size 1400x1400 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize1600` | `Resize1600` | Resize (1600x1600 pixels) | `kim_all resize --size 1600x1600 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize1920` | `Resize1920` | Resize (1920x1920 pixels) | `kim_all resize --size 1920x1920 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize2560` | `Resize2560` | Resize (2560x2560 pixels) | `kim_all resize --size 2560x2560 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize3440` | `Resize3440` | Resize (3440x3440 pixels) | `kim_all resize --size 3440x3440 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Resize3840` | `Resize3840` | Resize (3840x3840 pixels) | `kim_all resize --size 3840x3840 -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:ResizeCustom` | `ResizeCustom` | Resize custom… | `kim_all resize --custom -- %F` | large.jpg | authorized_overwrite |
| `kim_compressandresize.desktop:ResizePercent` | `ResizePercent` | Resize by percentage… | `kim_all resize --custom-percent -- %F` | large.jpg, unicode photo ü [1].jpg | authorized_overwrite |
| `kim_compressandresize.desktop:Web128` | `Web128` | Web thumbnail: 128x128 at 75 % | `kim_all webexport --size 128x128 --quality 75 -- %F` | profile-wide.jpg | derived |
| `kim_compressandresize.desktop:Web600` | `Web600` | Web export: 600x600 at 75 % | `kim_all webexport --size 600x600 --quality 75 -- %F` | profile-wide.jpg | derived |
| `kim_compressandresize.desktop:Web800` | `Web800` | Web export: 800x800 at 75 % | `kim_all webexport --size 800x800 --quality 75 -- %F` | profile-wide.jpg | derived |
| `kim_compressandresize.desktop:Web1024` | `Web1024` | Web export: 1024x1024 at 75 % | `kim_all webexport --size 1024x1024 --quality 75 -- %F` | profile-wide.jpg | derived |
| `kim_compressandresize.desktop:Web1600` | `Web1600` | Web export: 1600x1600 at 75 % | `kim_all webexport --size 1600x1600 --quality 75 -- %F` | profile-wide.jpg | derived |
| `kim_compressandresize.desktop:WebKeep` | `WebKeep` | Web export, keep input format… | `kim_all webexport --size 1600x1600 --quality 75 --format keep -- %F` | profile-wide.jpg | derived |
| `kim_compressandresize.desktop:Emailfull` | `Emailfull` | Send by mail: Send original by mail | `kim_all resizeandsend --size full -- %F` | photo.jpg, wide.jpg | derived |
| `kim_compressandresize.desktop:Email1600x1600` | `Email1600x1600` | Send by mail: Resize to 1600px and email | `kim_all resizeandsend --size 1600x1600 -- %F` | photo.jpg, wide.jpg | derived |
| `kim_compressandresize.desktop:Email1200x1200` | `Email1200x1200` | Send by mail: Resize to 1200px and email | `kim_all resizeandsend --size 1200x1200 -- %F` | photo.jpg, wide.jpg | derived |
| `kim_compressandresize.desktop:Email800x800` | `Email800x800` | Send by mail: Resize to 800px and email | `kim_all resizeandsend --size 800x800 -- %F` | photo.jpg, wide.jpg | derived |
| `kim_compressandresize.desktop:Email600x600` | `Email600x600` | Send by mail: Resize to 600px and email | `kim_all resizeandsend --size 600x600 -- %F` | photo.jpg, wide.jpg | derived |
| `kim_compressandresize.desktop:Email300x300` | `Email300x300` | Send by mail: Resize to 300px and email | `kim_all resizeandsend --size 300x300 -- %F` | photo.jpg, wide.jpg | derived |

### Resize (300x300 pixels) — `kim_compressandresize.desktop:Resize300`

- **Menu path:** KIM6 → Resize, web export and email → Resize (300x300 pixels)
- **Dispatcher contract:** `kim_all resize --size 300x300 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (300x300 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (600x600 pixels) — `kim_compressandresize.desktop:Resize600`

- **Menu path:** KIM6 → Resize, web export and email → Resize (600x600 pixels)
- **Dispatcher contract:** `kim_all resize --size 600x600 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (600x600 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (800x800 pixels) — `kim_compressandresize.desktop:Resize800`

- **Menu path:** KIM6 → Resize, web export and email → Resize (800x800 pixels)
- **Dispatcher contract:** `kim_all resize --size 800x800 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (800x800 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (1024x1024 pixels) — `kim_compressandresize.desktop:Resize1024`

- **Menu path:** KIM6 → Resize, web export and email → Resize (1024x1024 pixels)
- **Dispatcher contract:** `kim_all resize --size 1024x1024 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (1024x1024 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (1280x1280 pixels) — `kim_compressandresize.desktop:Resize1280`

- **Menu path:** KIM6 → Resize, web export and email → Resize (1280x1280 pixels)
- **Dispatcher contract:** `kim_all resize --size 1280x1280 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (1280x1280 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (1400x1400 pixels) — `kim_compressandresize.desktop:Resize1400`

- **Menu path:** KIM6 → Resize, web export and email → Resize (1400x1400 pixels)
- **Dispatcher contract:** `kim_all resize --size 1400x1400 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (1400x1400 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (1600x1600 pixels) — `kim_compressandresize.desktop:Resize1600`

- **Menu path:** KIM6 → Resize, web export and email → Resize (1600x1600 pixels)
- **Dispatcher contract:** `kim_all resize --size 1600x1600 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (1600x1600 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (1920x1920 pixels) — `kim_compressandresize.desktop:Resize1920`

- **Menu path:** KIM6 → Resize, web export and email → Resize (1920x1920 pixels)
- **Dispatcher contract:** `kim_all resize --size 1920x1920 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (1920x1920 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (2560x2560 pixels) — `kim_compressandresize.desktop:Resize2560`

- **Menu path:** KIM6 → Resize, web export and email → Resize (2560x2560 pixels)
- **Dispatcher contract:** `kim_all resize --size 2560x2560 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (2560x2560 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (3440x3440 pixels) — `kim_compressandresize.desktop:Resize3440`

- **Menu path:** KIM6 → Resize, web export and email → Resize (3440x3440 pixels)
- **Dispatcher contract:** `kim_all resize --size 3440x3440 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (3440x3440 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize (3840x3840 pixels) — `kim_compressandresize.desktop:Resize3840`

- **Menu path:** KIM6 → Resize, web export and email → Resize (3840x3840 pixels)
- **Dispatcher contract:** `kim_all resize --size 3840x3840 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize (3840x3840 pixels) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize custom… — `kim_compressandresize.desktop:ResizeCustom`

- **Menu path:** KIM6 → Resize, web export and email → Resize custom…
- **Dispatcher contract:** `kim_all resize --custom -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom geometry or percentage where requested.; Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize custom… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Resize by percentage… — `kim_compressandresize.desktop:ResizePercent`

- **Menu path:** KIM6 → Resize, web export and email → Resize by percentage…
- **Dispatcher contract:** `kim_all resize --custom-percent -- %F`
- **Select for the Dolphin context menu:** large.jpg, unicode photo ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom geometry or percentage where requested.; Create or overwrite policy when not fixed by KIM_POLICY.
- **Expected:** A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Confirm the dialog/action title matches: Resize by percentage… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Web thumbnail: 128x128 at 75 % — `kim_compressandresize.desktop:Web128`

- **Menu path:** KIM6 → Resize, web export and email → Web thumbnail: 128x128 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 128x128 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Expected:** A distinct validated derivative in the selected export directory; never the original.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Confirm the dialog/action title matches: Web thumbnail: 128x128 at 75 % Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Web export: 600x600 at 75 % — `kim_compressandresize.desktop:Web600`

- **Menu path:** KIM6 → Resize, web export and email → Web export: 600x600 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 600x600 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Expected:** A distinct validated derivative in the selected export directory; never the original.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Confirm the dialog/action title matches: Web export: 600x600 at 75 % Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Web export: 800x800 at 75 % — `kim_compressandresize.desktop:Web800`

- **Menu path:** KIM6 → Resize, web export and email → Web export: 800x800 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 800x800 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Expected:** A distinct validated derivative in the selected export directory; never the original.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Confirm the dialog/action title matches: Web export: 800x800 at 75 % Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Web export: 1024x1024 at 75 % — `kim_compressandresize.desktop:Web1024`

- **Menu path:** KIM6 → Resize, web export and email → Web export: 1024x1024 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 1024x1024 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Expected:** A distinct validated derivative in the selected export directory; never the original.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Confirm the dialog/action title matches: Web export: 1024x1024 at 75 % Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Web export: 1600x1600 at 75 % — `kim_compressandresize.desktop:Web1600`

- **Menu path:** KIM6 → Resize, web export and email → Web export: 1600x1600 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Expected:** A distinct validated derivative in the selected export directory; never the original.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Confirm the dialog/action title matches: Web export: 1600x1600 at 75 % Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Web export, keep input format… — `kim_compressandresize.desktop:WebKeep`

- **Menu path:** KIM6 → Resize, web export and email → Web export, keep input format…
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --quality 75 --format keep -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Expected:** A distinct validated derivative in the selected export directory; never the original.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Confirm the dialog/action title matches: Web export, keep input format… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Send by mail: Send original by mail — `kim_compressandresize.desktop:Emailfull`

- **Menu path:** KIM6 → Resize, web export and email → Send by mail: Send original by mail
- **Dispatcher contract:** `kim_all resizeandsend --size full -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Expected:** A mail draft with only prepared image attachments; attachment storage is isolated under this QA workspace when using its isolated Dolphin session.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Confirm the dialog/action title matches: Send by mail: Send original by mail Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Send by mail: Resize to 1600px and email — `kim_compressandresize.desktop:Email1600x1600`

- **Menu path:** KIM6 → Resize, web export and email → Send by mail: Resize to 1600px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 1600x1600 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Expected:** A mail draft with only prepared image attachments; attachment storage is isolated under this QA workspace when using its isolated Dolphin session.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Confirm the dialog/action title matches: Send by mail: Resize to 1600px and email Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Send by mail: Resize to 1200px and email — `kim_compressandresize.desktop:Email1200x1200`

- **Menu path:** KIM6 → Resize, web export and email → Send by mail: Resize to 1200px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 1200x1200 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Expected:** A mail draft with only prepared image attachments; attachment storage is isolated under this QA workspace when using its isolated Dolphin session.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Confirm the dialog/action title matches: Send by mail: Resize to 1200px and email Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Send by mail: Resize to 800px and email — `kim_compressandresize.desktop:Email800x800`

- **Menu path:** KIM6 → Resize, web export and email → Send by mail: Resize to 800px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 800x800 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Expected:** A mail draft with only prepared image attachments; attachment storage is isolated under this QA workspace when using its isolated Dolphin session.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Confirm the dialog/action title matches: Send by mail: Resize to 800px and email Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Send by mail: Resize to 600px and email — `kim_compressandresize.desktop:Email600x600`

- **Menu path:** KIM6 → Resize, web export and email → Send by mail: Resize to 600px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 600x600 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Expected:** A mail draft with only prepared image attachments; attachment storage is isolated under this QA workspace when using its isolated Dolphin session.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Confirm the dialog/action title matches: Send by mail: Resize to 600px and email Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Send by mail: Resize to 300px and email — `kim_compressandresize.desktop:Email300x300`

- **Menu path:** KIM6 → Resize, web export and email → Send by mail: Resize to 300px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 300x300 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Expected:** A mail draft with only prepared image attachments; attachment storage is isolated under this QA workspace when using its isolated Dolphin session.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Confirm the dialog/action title matches: Send by mail: Resize to 300px and email Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

## Video tools (`kim_compressandresizevideo.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_compressandresizevideo.desktop:Videohd72017265orig` | `Videohd72017265orig` | Transcode 720 good H.265 (original container) | `kim_all video --size hd720 --crf 17 --codec libx265 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72017265mp4` | `Videohd72017265mp4` | Transcode 720 good H.265 (MP4) | `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72017264orig` | `Videohd72017264orig` | Transcode 720 good H.264 (original container) | `kim_all video --size hd720 --crf 17 --codec libx264 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72017264mp4` | `Videohd72017264mp4` | Transcode 720 good H.264 (MP4) | `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F` | video-silent.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72023265orig` | `Videohd72023265orig` | Transcode 720 medium H.265 (original container) | `kim_all video --size hd720 --crf 23 --codec libx265 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72023265mp4` | `Videohd72023265mp4` | Transcode 720 medium H.265 (MP4) | `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72023264orig` | `Videohd72023264orig` | Transcode 720 medium H.264 (original container) | `kim_all video --size hd720 --crf 23 --codec libx264 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72023264mp4` | `Videohd72023264mp4` | Transcode 720 medium H.264 (MP4) | `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72029265orig` | `Videohd72029265orig` | Transcode 720 smaller file H.265 (original container) | `kim_all video --size hd720 --crf 29 --codec libx265 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72029265mp4` | `Videohd72029265mp4` | Transcode 720 smaller file H.265 (MP4) | `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72029264orig` | `Videohd72029264orig` | Transcode 720 smaller file H.264 (original container) | `kim_all video --size hd720 --crf 29 --codec libx264 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd72029264mp4` | `Videohd72029264mp4` | Transcode 720 smaller file H.264 (MP4) | `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108017265orig` | `Videohd108017265orig` | Transcode 1080 good H.265 (original container) | `kim_all video --size hd1080 --crf 17 --codec libx265 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108017265mp4` | `Videohd108017265mp4` | Transcode 1080 good H.265 (MP4) | `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108017264orig` | `Videohd108017264orig` | Transcode 1080 good H.264 (original container) | `kim_all video --size hd1080 --crf 17 --codec libx264 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108017264mp4` | `Videohd108017264mp4` | Transcode 1080 good H.264 (MP4) | `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108023265orig` | `Videohd108023265orig` | Transcode 1080 medium H.265 (original container) | `kim_all video --size hd1080 --crf 23 --codec libx265 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108023265mp4` | `Videohd108023265mp4` | Transcode 1080 medium H.265 (MP4) | `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108023264orig` | `Videohd108023264orig` | Transcode 1080 medium H.264 (original container) | `kim_all video --size hd1080 --crf 23 --codec libx264 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108023264mp4` | `Videohd108023264mp4` | Transcode 1080 medium H.264 (MP4) | `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108029265orig` | `Videohd108029265orig` | Transcode 1080 smaller file H.265 (original container) | `kim_all video --size hd1080 --crf 29 --codec libx265 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108029265mp4` | `Videohd108029265mp4` | Transcode 1080 smaller file H.265 (MP4) | `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108029264orig` | `Videohd108029264orig` | Transcode 1080 smaller file H.264 (original container) | `kim_all video --size hd1080 --crf 29 --codec libx264 --container orig -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Videohd108029264mp4` | `Videohd108029264mp4` | Transcode 1080 smaller file H.264 (MP4) | `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Av1hd720High` | `Av1hd720High` | AV1 720p high quality | `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Av1hd720Balanced` | `Av1hd720Balanced` | AV1 720p balanced | `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F` | video-silent.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Av1hd1080High` | `Av1hd1080High` | AV1 1080p high quality | `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Av1hd1080Balanced` | `Av1hd1080Balanced` | AV1 1080p balanced | `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:Av1Custom` | `Av1Custom` | Custom AV1 settings… | `kim_all video --size hd1080 --codec av1 --av1-quality custom --container mp4 -- %F` | video-audio.mp4 | authorized_overwrite |
| `kim_compressandresizevideo.desktop:VideoFrameAt` | `VideoFrameAt` | Extract frame at timestamp… | `kim_all videoframes --mode single --format png --interactive -- %F` | video-audio.mp4 | derived |
| `kim_compressandresizevideo.desktop:VideoThumbnail` | `VideoThumbnail` | Extract automatic thumbnail | `kim_all videoframes --mode thumbnail --format jpg -- %F` | video-audio.mp4 | derived |
| `kim_compressandresizevideo.desktop:VideoContactSheet` | `VideoContactSheet` | Create video contact sheet… | `kim_all videoframes --mode contact --format jpg --interactive -- %F` | video-audio.mp4 | derived |
| `kim_compressandresizevideo.desktop:ExtractVideoAudio` | `ExtractVideoAudio` | Extract audio… | `kim_all videoaudio --mode extract --format m4a --interactive -- %F` | video-multiaudio.mkv | derived |
| `kim_compressandresizevideo.desktop:MuteVideo` | `MuteVideo` | Remove audio (copy video) | `kim_all videoaudio --mode mute -- %F` | video-multiaudio.mkv | derived |
| `kim_compressandresizevideo.desktop:VideoToGif` | `VideoToGif` | Create animated GIF from video… | `kim_all videogif --interactive -- %F` | video-audio.mp4 | derived |
| `kim_compressandresizevideo.desktop:Manual` | `Manual` | KIM6 Manual | `kim_all manual` | video-audio.mp4 | none |
| `kim_compressandresizevideo.desktop:License` | `License` | License | `kim_all license` | video-audio.mp4 | none |
| `kim_compressandresizevideo.desktop:About` | `About` | About KIM6 | `kim_all about` | video-audio.mp4 | none |

### Transcode 720 good H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd72017265orig`

- **Menu path:** KIM6 → Video tools → Transcode 720 good H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 good H.265 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 good H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd72017265mp4`

- **Menu path:** KIM6 → Video tools → Transcode 720 good H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 good H.265 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 good H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd72017264orig`

- **Menu path:** KIM6 → Video tools → Transcode 720 good H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 good H.264 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 good H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd72017264mp4`

- **Menu path:** KIM6 → Video tools → Transcode 720 good H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-silent.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 good H.264 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 medium H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd72023265orig`

- **Menu path:** KIM6 → Video tools → Transcode 720 medium H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 medium H.265 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 medium H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd72023265mp4`

- **Menu path:** KIM6 → Video tools → Transcode 720 medium H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 medium H.265 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 medium H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd72023264orig`

- **Menu path:** KIM6 → Video tools → Transcode 720 medium H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 medium H.264 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 medium H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd72023264mp4`

- **Menu path:** KIM6 → Video tools → Transcode 720 medium H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 medium H.264 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 smaller file H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd72029265orig`

- **Menu path:** KIM6 → Video tools → Transcode 720 smaller file H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 smaller file H.265 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 smaller file H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd72029265mp4`

- **Menu path:** KIM6 → Video tools → Transcode 720 smaller file H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 smaller file H.265 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 smaller file H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd72029264orig`

- **Menu path:** KIM6 → Video tools → Transcode 720 smaller file H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 smaller file H.264 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 720 smaller file H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd72029264mp4`

- **Menu path:** KIM6 → Video tools → Transcode 720 smaller file H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 720 smaller file H.264 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 good H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd108017265orig`

- **Menu path:** KIM6 → Video tools → Transcode 1080 good H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 good H.265 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 good H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd108017265mp4`

- **Menu path:** KIM6 → Video tools → Transcode 1080 good H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 good H.265 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 good H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd108017264orig`

- **Menu path:** KIM6 → Video tools → Transcode 1080 good H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 good H.264 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 good H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd108017264mp4`

- **Menu path:** KIM6 → Video tools → Transcode 1080 good H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 good H.264 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 medium H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd108023265orig`

- **Menu path:** KIM6 → Video tools → Transcode 1080 medium H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 medium H.265 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 medium H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd108023265mp4`

- **Menu path:** KIM6 → Video tools → Transcode 1080 medium H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 medium H.265 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 medium H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd108023264orig`

- **Menu path:** KIM6 → Video tools → Transcode 1080 medium H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 medium H.264 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 medium H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd108023264mp4`

- **Menu path:** KIM6 → Video tools → Transcode 1080 medium H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 medium H.264 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 smaller file H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd108029265orig`

- **Menu path:** KIM6 → Video tools → Transcode 1080 smaller file H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 smaller file H.265 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 smaller file H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd108029265mp4`

- **Menu path:** KIM6 → Video tools → Transcode 1080 smaller file H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 smaller file H.265 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 smaller file H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd108029264orig`

- **Menu path:** KIM6 → Video tools → Transcode 1080 smaller file H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 smaller file H.264 (original container) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Transcode 1080 smaller file H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd108029264mp4`

- **Menu path:** KIM6 → Video tools → Transcode 1080 smaller file H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Transcode 1080 smaller file H.264 (MP4) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### AV1 720p high quality — `kim_compressandresizevideo.desktop:Av1hd720High`

- **Menu path:** KIM6 → Video tools → AV1 720p high quality
- **Dispatcher contract:** `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: AV1 720p high quality Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### AV1 720p balanced — `kim_compressandresizevideo.desktop:Av1hd720Balanced`

- **Menu path:** KIM6 → Video tools → AV1 720p balanced
- **Dispatcher contract:** `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-silent.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: AV1 720p balanced Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### AV1 1080p high quality — `kim_compressandresizevideo.desktop:Av1hd1080High`

- **Menu path:** KIM6 → Video tools → AV1 1080p high quality
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: AV1 1080p high quality Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### AV1 1080p balanced — `kim_compressandresizevideo.desktop:Av1hd1080Balanced`

- **Menu path:** KIM6 → Video tools → AV1 1080p balanced
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: AV1 1080p balanced Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Custom AV1 settings… — `kim_compressandresizevideo.desktop:Av1Custom`

- **Menu path:** KIM6 → Video tools → Custom AV1 settings…
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality custom --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** AV1 custom quality/speed when requested; output policy is selected by the action.
- **Expected:** A validated encoded video in the case directory, with the selected codec/container preset.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Confirm the dialog/action title matches: Custom AV1 settings… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Extract frame at timestamp… — `kim_compressandresizevideo.desktop:VideoFrameAt`

- **Menu path:** KIM6 → Video tools → Extract frame at timestamp…
- **Dispatcher contract:** `kim_all videoframes --mode single --format png --interactive -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Timestamp or contact-sheet grid only for interactive entries; format is fixed by the menu preset.
- **Expected:** One extracted frame, thumbnail or labeled contact sheet in the case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick for contact sheets, qdbus, kdialog
- **Technical validation:** Automated: output image fully decodes and observed dimensions/frame count are reported. Human: check requested timestamp and contact-sheet labels.
- **Human inspection:** Confirm the dialog/action title matches: Extract frame at timestamp… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Extract automatic thumbnail — `kim_compressandresizevideo.desktop:VideoThumbnail`

- **Menu path:** KIM6 → Video tools → Extract automatic thumbnail
- **Dispatcher contract:** `kim_all videoframes --mode thumbnail --format jpg -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Timestamp or contact-sheet grid only for interactive entries; format is fixed by the menu preset.
- **Expected:** One extracted frame, thumbnail or labeled contact sheet in the case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick for contact sheets, qdbus, kdialog
- **Technical validation:** Automated: output image fully decodes and observed dimensions/frame count are reported. Human: check requested timestamp and contact-sheet labels.
- **Human inspection:** Confirm the dialog/action title matches: Extract automatic thumbnail Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Create video contact sheet… — `kim_compressandresizevideo.desktop:VideoContactSheet`

- **Menu path:** KIM6 → Video tools → Create video contact sheet…
- **Dispatcher contract:** `kim_all videoframes --mode contact --format jpg --interactive -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Timestamp or contact-sheet grid only for interactive entries; format is fixed by the menu preset.
- **Expected:** One extracted frame, thumbnail or labeled contact sheet in the case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick for contact sheets, qdbus, kdialog
- **Technical validation:** Automated: output image fully decodes and observed dimensions/frame count are reported. Human: check requested timestamp and contact-sheet labels.
- **Human inspection:** Confirm the dialog/action title matches: Create video contact sheet… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Extract audio… — `kim_compressandresizevideo.desktop:ExtractVideoAudio`

- **Menu path:** KIM6 → Video tools → Extract audio…
- **Dispatcher contract:** `kim_all videoaudio --mode extract --format m4a --interactive -- %F`
- **Select for the Dolphin context menu:** video-multiaudio.mkv
- **Files passed to dispatcher:** yes
- **Interactive choices:** Audio format only for the extract entry; mute has no format dialog.
- **Expected:** An extracted audio file or muted derived video in the case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, audio encoder as requested
- **Technical validation:** ffprobe confirms audio codec/container and stream count, or confirms no audio after mute; full decode and approximate duration are checked.
- **Human inspection:** Confirm the dialog/action title matches: Extract audio… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Remove audio (copy video) — `kim_compressandresizevideo.desktop:MuteVideo`

- **Menu path:** KIM6 → Video tools → Remove audio (copy video)
- **Dispatcher contract:** `kim_all videoaudio --mode mute -- %F`
- **Select for the Dolphin context menu:** video-multiaudio.mkv
- **Files passed to dispatcher:** yes
- **Interactive choices:** Audio format only for the extract entry; mute has no format dialog.
- **Expected:** An extracted audio file or muted derived video in the case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, audio encoder as requested
- **Technical validation:** ffprobe confirms audio codec/container and stream count, or confirms no audio after mute; full decode and approximate duration are checked.
- **Human inspection:** Confirm the dialog/action title matches: Remove audio (copy video) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Create animated GIF from video… — `kim_compressandresizevideo.desktop:VideoToGif`

- **Menu path:** KIM6 → Video tools → Create animated GIF from video…
- **Dispatcher contract:** `kim_all videogif --interactive -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose interval, frame rate, width and loop behavior.
- **Expected:** A validated animated GIF for the chosen video interval in the case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog
- **Technical validation:** Automated: GIF fully decodes, has at least two frames, and observed dimensions are reported. Human: inspect timing and loop behavior.
- **Human inspection:** Confirm the dialog/action title matches: Create animated GIF from video… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### KIM6 Manual — `kim_compressandresizevideo.desktop:Manual`

- **Menu path:** KIM6 → Video tools → KIM6 Manual
- **Dispatcher contract:** `kim_all manual`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Expected:** Installed docs/index.html and its stylesheet open.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Manual renders and stylesheet loads.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### License — `kim_compressandresizevideo.desktop:License`

- **Menu path:** KIM6 → Video tools → License
- **Dispatcher contract:** `kim_all license`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Expected:** Installed LICENSE.md opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Opened document is the installed GPL license.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### About KIM6 — `kim_compressandresizevideo.desktop:About`

- **Menu path:** KIM6 → Video tools → About KIM6
- **Dispatcher contract:** `kim_all about`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Expected:** KDialog About text opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** kdialog
- **Technical validation:** Dialog is legible and identifies KIM6.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

## Convert, rotate and flip (`kim_convertandrotate.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_convertandrotate.desktop:ConvertJPG` | `ConvertJPG` | Convert to JPEG | `kim_all convert --format jpg -- %F` | orientation-6.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertPNG` | `ConvertPNG` | Convert to PNG | `kim_all convert --format png -- %F` | transparent.png | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertGIF` | `ConvertGIF` | Convert to GIF | `kim_all convert --format gif -- %F` | animated.gif | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertBMP` | `ConvertBMP` | Convert to BMP5 bitmap | `kim_all convert --format bmp --bmp5 -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertTIFF` | `ConvertTIFF` | Convert to TIFF | `kim_all convert --format tiff -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertPDF` | `ConvertPDF` | Convert to PDF | `kim_all convert --format pdf -- %F` | photo.tif | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertWEBP` | `ConvertWEBP` | Convert to WebP | `kim_all convert --format webp -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertAVIF` | `ConvertAVIF` | Convert to AVIF | `kim_all convert --format avif -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertHEIC` | `ConvertHEIC` | Convert to HEIC/HEIF | `kim_all convert --format heic -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertJXL` | `ConvertJXL` | Convert to JPEG XL | `kim_all convert --format jxl -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertJP2Lossless` | `ConvertJP2Lossless` | Convert to JPEG 2000 (lossless) | `kim_all convert --format jp2 --jp2-mode lossless -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertJP2Lossy` | `ConvertJP2Lossy` | Convert to JPEG 2000 (lossy) | `kim_all convert --format jp2 --jp2-mode lossy -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertCustom` | `ConvertCustom` | Convert to custom format… | `kim_all convert --custom-format -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:Rotateexif` | `Rotateexif` | Auto-rotate using EXIF | `kim_all rotate --exif -- %F` | orientation-6.jpg | in_place |
| `kim_convertandrotate.desktop:Rotate90` | `Rotate90` | Rotate 90° | `kim_all rotate --angle 90 -- %F` | photo.jpg | in_place |
| `kim_convertandrotate.desktop:Rotate180` | `Rotate180` | Rotate 180° | `kim_all rotate --angle 180 -- %F` | photo.jpg | in_place |
| `kim_convertandrotate.desktop:Rotate270` | `Rotate270` | Rotate 270° | `kim_all rotate --angle 270 -- %F` | photo.jpg | in_place |
| `kim_convertandrotate.desktop:RotateCustom` | `RotateCustom` | Rotate custom angle… | `kim_all rotate --custom -- %F` | photo.jpg | in_place |
| `kim_convertandrotate.desktop:FlipVertical` | `FlipVertical` | Flip vertically | `kim_all flipflop flip -- %F` | photo.jpg | in_place |
| `kim_convertandrotate.desktop:FlipHorizontal` | `FlipHorizontal` | Flip horizontally | `kim_all flipflop flop -- %F` | photo.jpg | in_place |

### Convert to JPEG — `kim_convertandrotate.desktop:ConvertJPG`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to JPEG
- **Dispatcher contract:** `kim_all convert --format jpg -- %F`
- **Select for the Dolphin context menu:** orientation-6.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to JPEG Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to PNG — `kim_convertandrotate.desktop:ConvertPNG`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to PNG
- **Dispatcher contract:** `kim_all convert --format png -- %F`
- **Select for the Dolphin context menu:** transparent.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to PNG Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to GIF — `kim_convertandrotate.desktop:ConvertGIF`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to GIF
- **Dispatcher contract:** `kim_all convert --format gif -- %F`
- **Select for the Dolphin context menu:** animated.gif
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to GIF Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to BMP5 bitmap — `kim_convertandrotate.desktop:ConvertBMP`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to BMP5 bitmap
- **Dispatcher contract:** `kim_all convert --format bmp --bmp5 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to BMP5 bitmap Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to TIFF — `kim_convertandrotate.desktop:ConvertTIFF`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to TIFF
- **Dispatcher contract:** `kim_all convert --format tiff -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to TIFF Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to PDF — `kim_convertandrotate.desktop:ConvertPDF`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to PDF
- **Dispatcher contract:** `kim_all convert --format pdf -- %F`
- **Select for the Dolphin context menu:** photo.tif
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to PDF Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to WebP — `kim_convertandrotate.desktop:ConvertWEBP`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to WebP
- **Dispatcher contract:** `kim_all convert --format webp -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to WebP Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to AVIF — `kim_convertandrotate.desktop:ConvertAVIF`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to AVIF
- **Dispatcher contract:** `kim_all convert --format avif -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to AVIF Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to HEIC/HEIF — `kim_convertandrotate.desktop:ConvertHEIC`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to HEIC/HEIF
- **Dispatcher contract:** `kim_all convert --format heic -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to HEIC/HEIF Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to JPEG XL — `kim_convertandrotate.desktop:ConvertJXL`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to JPEG XL
- **Dispatcher contract:** `kim_all convert --format jxl -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to JPEG XL Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to JPEG 2000 (lossless) — `kim_convertandrotate.desktop:ConvertJP2Lossless`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to JPEG 2000 (lossless)
- **Dispatcher contract:** `kim_all convert --format jp2 --jp2-mode lossless -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to JPEG 2000 (lossless) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to JPEG 2000 (lossy) — `kim_convertandrotate.desktop:ConvertJP2Lossy`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to JPEG 2000 (lossy)
- **Dispatcher contract:** `kim_all convert --format jp2 --jp2-mode lossy -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to JPEG 2000 (lossy) Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Convert to custom format… — `kim_convertandrotate.desktop:ConvertCustom`

- **Menu path:** KIM6 → Convert, rotate and flip → Convert to custom format…
- **Dispatcher contract:** `kim_all convert --custom-format -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Expected:** A validated output in the selected target format, in the case directory; choose it in the save dialog.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Confirm the dialog/action title matches: Convert to custom format… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Auto-rotate using EXIF — `kim_convertandrotate.desktop:Rotateexif`

- **Menu path:** KIM6 → Convert, rotate and flip → Auto-rotate using EXIF
- **Dispatcher contract:** `kim_all rotate --exif -- %F`
- **Select for the Dolphin context menu:** orientation-6.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Expected:** The selected disposable copy is transformed in place after validation.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Confirm the dialog/action title matches: Auto-rotate using EXIF Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Rotate 90° — `kim_convertandrotate.desktop:Rotate90`

- **Menu path:** KIM6 → Convert, rotate and flip → Rotate 90°
- **Dispatcher contract:** `kim_all rotate --angle 90 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Expected:** The selected disposable copy is transformed in place after validation.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Confirm the dialog/action title matches: Rotate 90° Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Rotate 180° — `kim_convertandrotate.desktop:Rotate180`

- **Menu path:** KIM6 → Convert, rotate and flip → Rotate 180°
- **Dispatcher contract:** `kim_all rotate --angle 180 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Expected:** The selected disposable copy is transformed in place after validation.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Confirm the dialog/action title matches: Rotate 180° Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Rotate 270° — `kim_convertandrotate.desktop:Rotate270`

- **Menu path:** KIM6 → Convert, rotate and flip → Rotate 270°
- **Dispatcher contract:** `kim_all rotate --angle 270 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Expected:** The selected disposable copy is transformed in place after validation.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Confirm the dialog/action title matches: Rotate 270° Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Rotate custom angle… — `kim_convertandrotate.desktop:RotateCustom`

- **Menu path:** KIM6 → Convert, rotate and flip → Rotate custom angle…
- **Dispatcher contract:** `kim_all rotate --custom -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom angle for the custom entry; output policy follows the in-place action dialog.
- **Expected:** The selected disposable copy is transformed in place after validation.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Confirm the dialog/action title matches: Rotate custom angle… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Flip vertically — `kim_convertandrotate.desktop:FlipVertical`

- **Menu path:** KIM6 → Convert, rotate and flip → Flip vertically
- **Dispatcher contract:** `kim_all flipflop flip -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Confirm the horizontal/vertical direction shown in the visible label.
- **Expected:** The selected disposable copy is flipped/flopped in place after validation.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode and dimensions are valid; compare asymmetric shapes to confirm axis.
- **Human inspection:** Confirm the dialog/action title matches: Flip vertically Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Flip horizontally — `kim_convertandrotate.desktop:FlipHorizontal`

- **Menu path:** KIM6 → Convert, rotate and flip → Flip horizontally
- **Dispatcher contract:** `kim_all flipflop flop -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Confirm the horizontal/vertical direction shown in the visible label.
- **Expected:** The selected disposable copy is flipped/flopped in place after validation.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode and dimensions are valid; compare asymmetric shapes to confirm axis.
- **Human inspection:** Confirm the dialog/action title matches: Flip horizontally Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

## Publish and organize (`kim_publication.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_publication.desktop:Gallery` | `Gallery` | Create an HTML gallery… | `kim_all gallery -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Collage` | `Collage` | Create a photo collage… | `kim_all pelemele -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Rename` | `Rename` | Rename images… | `kim_all rename interactive -- %F` | dated-photo.jpg, sequence-red.png, -leading ü [1].jpg | rename |
| `kim_publication.desktop:SortByDate` | `SortByDate` | Rename by EXIF date… | `kim_all rename exifdate -- %F` | dated-photo.jpg, sequence-red.png, -leading ü [1].jpg | rename |
| `kim_publication.desktop:StripMetadata` | `StripMetadata` | Strip metadata… | `kim_all stripmeta -- %F` | metadata.jpg | authorized_overwrite |
| `kim_publication.desktop:StripGPS` | `StripGPS` | Remove GPS coordinates… | `kim_all stripmeta --mode gps -- %F` | metadata.jpg | authorized_overwrite |
| `kim_publication.desktop:RemoveAIMetadata` | `RemoveAIMetadata` | Remove recognized AI metadata… | `kim_all stripmeta --mode ai -- %F` | metadata.jpg | authorized_overwrite |
| `kim_publication.desktop:SetCopyright` | `SetCopyright` | Set creator and copyright… | `kim_all copyright --interactive -- %F` | metadata.jpg | authorized_overwrite |
| `kim_publication.desktop:AdjustCaptureTime` | `AdjustCaptureTime` | Adjust camera timestamps… | `kim_all timeshift --interactive -- %F` | metadata.jpg | authorized_overwrite |
| `kim_publication.desktop:DateSync` | `DateSync` | Synchronize photo/file dates… | `kim_all datesync --interactive -- %F` | metadata.jpg | authorized_overwrite |
| `kim_publication.desktop:Slideshow` | `Slideshow` | Create MP4 slideshow… | `kim_all slideshow --interactive -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Album` | `Album` | Create a PDF album… | `kim_all album -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Print` | `Print` | Create a print-layout PDF… | `kim_all print -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:TiffJoin` | `TiffJoin` | Join images into a multi-page TIFF… | `kim_all tiffjoin -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Animation` | `Animation` | Create an animated GIF… | `kim_all animate -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Manual` | `Manual` | KIM6 Manual | `kim_all manual` | photo.jpg | none |
| `kim_publication.desktop:License` | `License` | License | `kim_all license` | photo.jpg | none |
| `kim_publication.desktop:About` | `About` | About KIM6 | `kim_all about` | photo.jpg | none |

### Create an HTML gallery… — `kim_publication.desktop:Gallery`

- **Menu path:** KIM6 → Publish and organize → Create an HTML gallery…
- **Dispatcher contract:** `kim_all gallery -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Enter gallery title/author and layout/output options.
- **Expected:** A complete gallery directory containing index.html, main images and thumbnails.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional xdg-open
- **Technical validation:** index.html and all relative image/thumbnail references exist.
- **Human inspection:** Confirm the dialog/action title matches: Create an HTML gallery… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Create a photo collage… — `kim_publication.desktop:Collage`

- **Menu path:** KIM6 → Publish and organize → Create a photo collage…
- **Dispatcher contract:** `kim_all pelemele -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose canvas/image size, layout, background, border, spacing/overlap and rotation/shadow options.
- **Expected:** A validated collage image in the chosen case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Image decodes and selected tile ordering/layout is visible.
- **Human inspection:** Confirm the dialog/action title matches: Create a photo collage… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Rename images… — `kim_publication.desktop:Rename`

- **Menu path:** KIM6 → Publish and organize → Rename images…
- **Dispatcher contract:** `kim_all rename interactive -- %F`
- **Select for the Dolphin context menu:** dated-photo.jpg, sequence-red.png, -leading ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose naming mode, sequence/base or EXIF date format, destination, and conflict behavior as prompted.
- **Expected:** The renamed/moved test files are in the case directory; originals remain in this disposable case when create mode is selected.
- **Source behavior:** `rename`. Inputs are case-local disposable copies.
- **Dependencies:** qdbus, kdialog, optional exiftool for EXIF-date mode
- **Technical validation:** Each selected byte hash appears under the expected new name; no unrelated entry is lost.
- **Human inspection:** Confirm the dialog/action title matches: Rename images… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Rename by EXIF date… — `kim_publication.desktop:SortByDate`

- **Menu path:** KIM6 → Publish and organize → Rename by EXIF date…
- **Dispatcher contract:** `kim_all rename exifdate -- %F`
- **Select for the Dolphin context menu:** dated-photo.jpg, sequence-red.png, -leading ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose naming mode, sequence/base or EXIF date format, destination, and conflict behavior as prompted.
- **Expected:** The renamed/moved test files are in the case directory; originals remain in this disposable case when create mode is selected.
- **Source behavior:** `rename`. Inputs are case-local disposable copies.
- **Dependencies:** qdbus, kdialog, optional exiftool for EXIF-date mode
- **Technical validation:** Each selected byte hash appears under the expected new name; no unrelated entry is lost.
- **Human inspection:** Confirm the dialog/action title matches: Rename by EXIF date… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Strip metadata… — `kim_publication.desktop:StripMetadata`

- **Menu path:** KIM6 → Publish and organize → Strip metadata…
- **Dispatcher contract:** `kim_all stripmeta -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Expected:** A validated stripped derivative or authorized replacement; use the requested metadata scope.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Confirm the dialog/action title matches: Strip metadata… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Remove GPS coordinates… — `kim_publication.desktop:StripGPS`

- **Menu path:** KIM6 → Publish and organize → Remove GPS coordinates…
- **Dispatcher contract:** `kim_all stripmeta --mode gps -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Expected:** A validated stripped derivative or authorized replacement; use the requested metadata scope.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Confirm the dialog/action title matches: Remove GPS coordinates… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Remove recognized AI metadata… — `kim_publication.desktop:RemoveAIMetadata`

- **Menu path:** KIM6 → Publish and organize → Remove recognized AI metadata…
- **Dispatcher contract:** `kim_all stripmeta --mode ai -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Expected:** A validated stripped derivative or authorized replacement; use the requested metadata scope.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Confirm the dialog/action title matches: Remove recognized AI metadata… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Set creator and copyright… — `kim_publication.desktop:SetCopyright`

- **Menu path:** KIM6 → Publish and organize → Set creator and copyright…
- **Dispatcher contract:** `kim_all copyright --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose creator, notice and/or usage-rights fields; blank fields are left unchanged.
- **Expected:** A validated image with selected rights fields, or a numbered derivative.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Creator/copyright fields read back; unrelated metadata and pixels remain.
- **Human inspection:** Confirm the dialog/action title matches: Set creator and copyright… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Adjust camera timestamps… — `kim_publication.desktop:AdjustCaptureTime`

- **Menu path:** KIM6 → Publish and organize → Adjust camera timestamps…
- **Dispatcher contract:** `kim_all timeshift --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose offset direction and the camera timestamp fields to shift.
- **Expected:** A validated image with shifted camera date tags, or a numbered derivative.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Selected camera date tags read back with expected offset; filesystem mtime unchanged.
- **Human inspection:** Confirm the dialog/action title matches: Adjust camera timestamps… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Synchronize photo/file dates… — `kim_publication.desktop:DateSync`

- **Menu path:** KIM6 → Publish and organize → Synchronize photo/file dates…
- **Dispatcher contract:** `kim_all datesync --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose EXIF-to-filesystem or filesystem-to-EXIF; file-to-EXIF also asks which date tags to update.
- **Expected:** Filesystem mtime or EXIF dates match the chosen direction; use the source copy in this case.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, qdbus, kdialog
- **Technical validation:** Compare EXIF date and filesystem mtime in the selected direction.
- **Human inspection:** Confirm the dialog/action title matches: Synchronize photo/file dates… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Create MP4 slideshow… — `kim_publication.desktop:Slideshow`

- **Menu path:** KIM6 → Publish and organize → Create MP4 slideshow…
- **Dispatcher contract:** `kim_all slideshow --interactive -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose slide duration, frame size/rate, background and ordering options.
- **Expected:** A silent H.264 MP4 in the chosen case directory, with slides in natural filename order.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick, identify, libx264, qdbus, kdialog
- **Technical validation:** Automated: ffprobe confirms H.264 MP4, observed dimensions, selected frame rate, approximate duration, frame count when reported, no audio, and full decode. Human: compare image order and dimensions to the interactive choices.
- **Human inspection:** Confirm the dialog/action title matches: Create MP4 slideshow… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Play the result or inspect it with the relevant viewer; verify motion, orientation, audio, and timing as appropriate.

### Create a PDF album… — `kim_publication.desktop:Album`

- **Menu path:** KIM6 → Publish and organize → Create a PDF album…
- **Dispatcher contract:** `kim_all album -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose one of the supported album layouts and output/title options.
- **Expected:** A multi-page PDF in the chosen case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, PDF delegate
- **Technical validation:** Automated: pdfinfo can read the PDF and reports a positive page count and physical page size. Human: compare page count, image order and layout to the selected options.
- **Human inspection:** Confirm the dialog/action title matches: Create a PDF album… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Create a print-layout PDF… — `kim_publication.desktop:Print`

- **Menu path:** KIM6 → Publish and organize → Create a print-layout PDF…
- **Dispatcher contract:** `kim_all print -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose one of the supported print layouts and page settings.
- **Expected:** A print-layout PDF in the chosen case directory.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, PDF delegate
- **Technical validation:** Automated: pdfinfo can read the PDF and reports a positive page count and physical page size. Human: compare page orientation and print layout to the chosen options.
- **Human inspection:** Confirm the dialog/action title matches: Create a print-layout PDF… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Join images into a multi-page TIFF… — `kim_publication.desktop:TiffJoin`

- **Menu path:** KIM6 → Publish and organize → Join images into a multi-page TIFF…
- **Dispatcher contract:** `kim_all tiffjoin -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose the output location/name; selected order is used.
- **Expected:** A multi-page TIFF in the chosen case directory, in selection order.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Automated: TIFF fully decodes and page count matches selected input frame count. Human: inspect page order.
- **Human inspection:** Confirm the dialog/action title matches: Join images into a multi-page TIFF… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### Create an animated GIF… — `kim_publication.desktop:Animation`

- **Menu path:** KIM6 → Publish and organize → Create an animated GIF…
- **Dispatcher contract:** `kim_all animate -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose frame delay and animation settings.
- **Expected:** An animated GIF in the chosen case directory, with the selected delay and loop behavior.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Automated: GIF fully decodes and frame count matches selected input frame count. Human: inspect frame order, delay and loop behavior.
- **Human inspection:** Confirm the dialog/action title matches: Create an animated GIF… Confirm cancellation closes the dialog without publishing an unwanted result. Inspect the output in this disposable case directory; do not use personal media. Compare visible colors, orientation, order, crop and framing with the input; automated checks cannot assess subjective quality.

### KIM6 Manual — `kim_publication.desktop:Manual`

- **Menu path:** KIM6 → Publish and organize → KIM6 Manual
- **Dispatcher contract:** `kim_all manual`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Expected:** Installed docs/index.html and its stylesheet open.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Manual renders and stylesheet loads.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### License — `kim_publication.desktop:License`

- **Menu path:** KIM6 → Publish and organize → License
- **Dispatcher contract:** `kim_all license`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Expected:** Installed LICENSE.md opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Opened document is the installed GPL license.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### About KIM6 — `kim_publication.desktop:About`

- **Menu path:** KIM6 → Publish and organize → About KIM6
- **Dispatcher contract:** `kim_all about`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Expected:** KDialog About text opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** kdialog
- **Technical validation:** Dialog is legible and identifies KIM6.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

## Status meanings

The CLI result log separates **GUI verified**, **CLI verified**, **GUI blocked by KDE**, and **Not tested**. Only a person invoking a menu in Dolphin can record GUI verification. `validate` performs technical checks only.
