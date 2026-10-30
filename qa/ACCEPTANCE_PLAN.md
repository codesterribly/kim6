# KIM6 Human Acceptance Plan

Generated from the five current service-menu templates: **108 menu actions**.

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

- **Menu path:** KIM6 — JPEG compression → JPEG quality: 10%
- **Dispatcher contract:** `kim_all compress --quality 10 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Use the menu preset at JPEG quality 10. Do not confuse this with resizing; it changes JPEG encoding quality.
- **Expected:** A JPEG tagged `_compressed` (normally `photo_compressed.jpg` with the default suffix setting).
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG quality: 10%’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### JPEG quality: 30% — `kim_compress.desktop:Compress30`

- **Menu path:** KIM6 — JPEG compression → JPEG quality: 30%
- **Dispatcher contract:** `kim_all compress --quality 30 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Use the menu preset at JPEG quality 30. Do not confuse this with resizing; it changes JPEG encoding quality.
- **Expected:** A JPEG tagged `_compressed` (normally `photo_compressed.jpg` with the default suffix setting).
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG quality: 30%’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### JPEG quality: 50% — `kim_compress.desktop:Compress50`

- **Menu path:** KIM6 — JPEG compression → JPEG quality: 50%
- **Dispatcher contract:** `kim_all compress --quality 50 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Use the menu preset at JPEG quality 50. Do not confuse this with resizing; it changes JPEG encoding quality.
- **Expected:** A JPEG tagged `_compressed` (normally `photo_compressed.jpg` with the default suffix setting).
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG quality: 50%’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### JPEG quality: 70% — `kim_compress.desktop:Compress70`

- **Menu path:** KIM6 — JPEG compression → JPEG quality: 70%
- **Dispatcher contract:** `kim_all compress --quality 70 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Use the menu preset at JPEG quality 70. Do not confuse this with resizing; it changes JPEG encoding quality.
- **Expected:** A JPEG tagged `_compressed` (normally `photo_compressed.jpg` with the default suffix setting).
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG quality: 70%’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### JPEG quality: 90% — `kim_compress.desktop:Compress90`

- **Menu path:** KIM6 — JPEG compression → JPEG quality: 90%
- **Dispatcher contract:** `kim_all compress --quality 90 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Use the menu preset at JPEG quality 90. Do not confuse this with resizing; it changes JPEG encoding quality.
- **Expected:** A JPEG tagged `_compressed` (normally `photo_compressed.jpg` with the default suffix setting).
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘JPEG quality: 90%’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Compress at custom quality… — `kim_compress.desktop:CompressCustom`

- **Menu path:** KIM6 — JPEG compression → Compress at custom quality…
- **Dispatcher contract:** `kim_all compress --custom -- %F`
- **Select for the Dolphin context menu:** -leading ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom quality when the menu entry is custom.; Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Enter a JPEG quality from 1 to 100 when prompted; use 50 for this check.
- **Expected:** A JPEG derivative tagged `_compressed`, or the explicitly selected overwrite result.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode.
- **Human inspection:** Check that the menu starts the operation named ‘Compress at custom quality…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

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

- **Menu path:** KIM6 — Compress, resize and web export → Resize (300x300 pixels)
- **Dispatcher contract:** `kim_all resize --size 300x300 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 300x300; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 300x300 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (300x300 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (600x600 pixels) — `kim_compressandresize.desktop:Resize600`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (600x600 pixels)
- **Dispatcher contract:** `kim_all resize --size 600x600 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 600x600; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 600x600 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (600x600 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (800x800 pixels) — `kim_compressandresize.desktop:Resize800`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (800x800 pixels)
- **Dispatcher contract:** `kim_all resize --size 800x800 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 800x800; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 800x800 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (800x800 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (1024x1024 pixels) — `kim_compressandresize.desktop:Resize1024`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (1024x1024 pixels)
- **Dispatcher contract:** `kim_all resize --size 1024x1024 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1024x1024; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1024x1024 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (1024x1024 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (1280x1280 pixels) — `kim_compressandresize.desktop:Resize1280`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (1280x1280 pixels)
- **Dispatcher contract:** `kim_all resize --size 1280x1280 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1280x1280; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1280x1280 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (1280x1280 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (1400x1400 pixels) — `kim_compressandresize.desktop:Resize1400`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (1400x1400 pixels)
- **Dispatcher contract:** `kim_all resize --size 1400x1400 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1400x1400; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1400x1400 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (1400x1400 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (1600x1600 pixels) — `kim_compressandresize.desktop:Resize1600`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (1600x1600 pixels)
- **Dispatcher contract:** `kim_all resize --size 1600x1600 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1600x1600; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1600x1600 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (1600x1600 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (1920x1920 pixels) — `kim_compressandresize.desktop:Resize1920`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (1920x1920 pixels)
- **Dispatcher contract:** `kim_all resize --size 1920x1920 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 1920x1920; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 1920x1920 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (1920x1920 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (2560x2560 pixels) — `kim_compressandresize.desktop:Resize2560`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (2560x2560 pixels)
- **Dispatcher contract:** `kim_all resize --size 2560x2560 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 2560x2560; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 2560x2560 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (2560x2560 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (3440x3440 pixels) — `kim_compressandresize.desktop:Resize3440`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (3440x3440 pixels)
- **Dispatcher contract:** `kim_all resize --size 3440x3440 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 3440x3440; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 3440x3440 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (3440x3440 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize (3840x3840 pixels) — `kim_compressandresize.desktop:Resize3840`

- **Menu path:** KIM6 — Compress, resize and web export → Resize (3840x3840 pixels)
- **Dispatcher contract:** `kim_all resize --size 3840x3840 -- %F`
- **Select for the Dolphin context menu:** large.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** The menu requests a maximum size of 3840x3840; keep the aspect ratio when the prompt offers geometry choices.
- **Expected:** A smaller image tagged `_resized`, within 3840x3840 bounds.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize (3840x3840 pixels)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Resize custom… — `kim_compressandresize.desktop:ResizeCustom`

- **Menu path:** KIM6 — Compress, resize and web export → Resize custom…
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

### Resize by percentage… — `kim_compressandresize.desktop:ResizePercent`

- **Menu path:** KIM6 — Compress, resize and web export → Resize by percentage…
- **Dispatcher contract:** `kim_all resize --custom-percent -- %F`
- **Select for the Dolphin context menu:** large.jpg, unicode photo ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom geometry or percentage where requested.; Create or overwrite policy when not fixed by KIM_POLICY.
- **Suggested choices:** Enter 50% in the resize percentage prompt (valid range 1–1000%).
- **Expected:** A resized derivative at half the source width and height, tagged `_resized`; check the decoded dimensions.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, actual format, frame count and dimensions are plausible for chosen geometry.
- **Human inspection:** Check that the menu starts the operation named ‘Resize by percentage…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Web thumbnail: 128x128 at 75 % — `kim_compressandresize.desktop:Web128`

- **Menu path:** KIM6 — Compress, resize and web export → Web thumbnail: 128x128 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 128x128 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 128x128 size and quality 75 preset; select this case folder as the export destination. Format: configured web format. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘Web thumbnail: 128x128 at 75 %’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Web export: 600x600 at 75 % — `kim_compressandresize.desktop:Web600`

- **Menu path:** KIM6 — Compress, resize and web export → Web export: 600x600 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 600x600 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 600x600 size and quality 75 preset; select this case folder as the export destination. Format: configured web format. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘Web export: 600x600 at 75 %’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Web export: 800x800 at 75 % — `kim_compressandresize.desktop:Web800`

- **Menu path:** KIM6 — Compress, resize and web export → Web export: 800x800 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 800x800 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 800x800 size and quality 75 preset; select this case folder as the export destination. Format: configured web format. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘Web export: 800x800 at 75 %’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Web export: 1024x1024 at 75 % — `kim_compressandresize.desktop:Web1024`

- **Menu path:** KIM6 — Compress, resize and web export → Web export: 1024x1024 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 1024x1024 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 1024x1024 size and quality 75 preset; select this case folder as the export destination. Format: configured web format. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘Web export: 1024x1024 at 75 %’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Web export: 1600x1600 at 75 % — `kim_compressandresize.desktop:Web1600`

- **Menu path:** KIM6 — Compress, resize and web export → Web export: 1600x1600 at 75 %
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --quality 75 -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 1600x1600 size and quality 75 preset; select this case folder as the export destination. Format: configured web format. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘Web export: 1600x1600 at 75 %’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Web export, keep input format… — `kim_compressandresize.desktop:WebKeep`

- **Menu path:** KIM6 — Compress, resize and web export → Web export, keep input format…
- **Dispatcher contract:** `kim_all webexport --size 1600x1600 --quality 75 --format keep -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Export destination and configured output format/color policy.; Never overwrites selected sources.
- **Suggested choices:** Use the 1600x1600 size and quality 75 preset; select this case folder as the export destination. Format: keep. The action always makes a derivative.
- **Expected:** A distinct web image in this case folder; the selected source remains unchanged.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Actual output format, dimensions and profile are checked; source remains byte-identical.
- **Human inspection:** Check that the menu starts the operation named ‘Web export, keep input format…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Send by mail: Send original by mail — `kim_compressandresize.desktop:Emailfull`

- **Menu path:** KIM6 — Compress, resize and web export → Send by mail: Send original by mail
- **Dispatcher contract:** `kim_all resizeandsend --size full -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Suggested choices:** Use the full mail preset. Inspect the draft's attachment list, then close the draft without sending.
- **Expected:** A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Send by mail: Send original by mail’. Check that the draft contains only the expected prepared images and do not send it.

### Send by mail: Resize to 1600px and email — `kim_compressandresize.desktop:Email1600x1600`

- **Menu path:** KIM6 — Compress, resize and web export → Send by mail: Resize to 1600px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 1600x1600 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Suggested choices:** Use the 1600x1600 mail preset. Inspect the draft's attachment list, then close the draft without sending.
- **Expected:** A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Send by mail: Resize to 1600px and email’. Check that the draft contains only the expected prepared images and do not send it.

### Send by mail: Resize to 1200px and email — `kim_compressandresize.desktop:Email1200x1200`

- **Menu path:** KIM6 — Compress, resize and web export → Send by mail: Resize to 1200px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 1200x1200 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Suggested choices:** Use the 1200x1200 mail preset. Inspect the draft's attachment list, then close the draft without sending.
- **Expected:** A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Send by mail: Resize to 1200px and email’. Check that the draft contains only the expected prepared images and do not send it.

### Send by mail: Resize to 800px and email — `kim_compressandresize.desktop:Email800x800`

- **Menu path:** KIM6 — Compress, resize and web export → Send by mail: Resize to 800px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 800x800 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Suggested choices:** Use the 800x800 mail preset. Inspect the draft's attachment list, then close the draft without sending.
- **Expected:** A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Send by mail: Resize to 800px and email’. Check that the draft contains only the expected prepared images and do not send it.

### Send by mail: Resize to 600px and email — `kim_compressandresize.desktop:Email600x600`

- **Menu path:** KIM6 — Compress, resize and web export → Send by mail: Resize to 600px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 600x600 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Suggested choices:** Use the 600x600 mail preset. Inspect the draft's attachment list, then close the draft without sending.
- **Expected:** A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Send by mail: Resize to 600px and email’. Check that the draft contains only the expected prepared images and do not send it.

### Send by mail: Resize to 300px and email — `kim_compressandresize.desktop:Email300x300`

- **Menu path:** KIM6 — Compress, resize and web export → Send by mail: Resize to 300px and email
- **Dispatcher contract:** `kim_all resizeandsend --size 300x300 -- %F`
- **Select for the Dolphin context menu:** photo.jpg, wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback.
- **Suggested choices:** Use the 300x300 mail preset. Inspect the draft's attachment list, then close the draft without sending.
- **Expected:** A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional mail client
- **Technical validation:** Draft contains only prepared files with valid formats; source hashes remain unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Send by mail: Resize to 300px and email’. Check that the draft contains only the expected prepared images and do not send it.

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
| `kim_compressandresizevideo.desktop:Manual` | `Manual` | KIM6 User Guide | `kim_all manual` | video-audio.mp4 | none |
| `kim_compressandresizevideo.desktop:License` | `License` | License | `kim_all license` | video-audio.mp4 | none |
| `kim_compressandresizevideo.desktop:About` | `About` | About KIM6 | `kim_all about` | video-audio.mp4 | none |

### Transcode 720 good H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd72017265orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 good H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 17, output size hd720, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 good H.265 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 good H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd72017265mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 good H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 17, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 good H.265 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 good H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd72017264orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 good H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 17, output size hd720, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 good H.264 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 good H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd72017264mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 good H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 17 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-silent.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 17, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 good H.264 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 medium H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd72023265orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 medium H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 23, output size hd720, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 medium H.265 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 medium H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd72023265mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 medium H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 23, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 medium H.265 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 medium H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd72023264orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 medium H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 23, output size hd720, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 medium H.264 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 medium H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd72023264mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 medium H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 23 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 23, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 medium H.264 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 smaller file H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd72029265orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 smaller file H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 29, output size hd720, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 smaller file H.265 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 smaller file H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd72029265mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 smaller file H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 29, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 smaller file H.265 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 smaller file H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd72029264orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 smaller file H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 29, output size hd720, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 smaller file H.264 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 720 smaller file H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd72029264mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 720 smaller file H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd720 --crf 29 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 29, output size hd720, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 720 smaller file H.264 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 good H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd108017265orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 good H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 17, output size hd1080, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 good H.265 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 good H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd108017265mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 good H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 17, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 good H.265 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 good H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd108017264orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 good H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 17, output size hd1080, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 good H.264 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 good H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd108017264mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 good H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 17 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 17, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 good H.264 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 medium H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd108023265orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 medium H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 23, output size hd1080, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 medium H.265 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 medium H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd108023265mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 medium H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 23, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 medium H.265 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 medium H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd108023264orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 medium H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 23, output size hd1080, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 medium H.264 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 medium H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd108023264mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 medium H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 23 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 23, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 medium H.264 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 smaller file H.265 (original container) — `kim_compressandresizevideo.desktop:Videohd108029265orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 smaller file H.265 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx265 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 29, output size hd1080, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 smaller file H.265 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 smaller file H.265 (MP4) — `kim_compressandresizevideo.desktop:Videohd108029265mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 smaller file H.265 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx265 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx265, CRF 29, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 smaller file H.265 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 smaller file H.264 (original container) — `kim_compressandresizevideo.desktop:Videohd108029264orig`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 smaller file H.264 (original container)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx264 --container orig -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 29, output size hd1080, container orig. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 smaller file H.264 (original container)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Transcode 1080 smaller file H.264 (MP4) — `kim_compressandresizevideo.desktop:Videohd108029264mp4`

- **Menu path:** KIM6 — Video transcoding → Transcode 1080 smaller file H.264 (MP4)
- **Dispatcher contract:** `kim_all video --size hd1080 --crf 29 --codec libx264 --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: libx264, CRF 29, output size hd1080, container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Transcode 1080 smaller file H.264 (MP4)’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### AV1 720p high quality — `kim_compressandresizevideo.desktop:Av1hd720High`

- **Menu path:** KIM6 — Video transcoding → AV1 720p high quality
- **Dispatcher contract:** `kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 high quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 high quality; output size hd720; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘AV1 720p high quality’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### AV1 720p balanced — `kim_compressandresizevideo.desktop:Av1hd720Balanced`

- **Menu path:** KIM6 — Video transcoding → AV1 720p balanced
- **Dispatcher contract:** `kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-silent.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 balanced quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 balanced quality; output size hd720; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘AV1 720p balanced’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### AV1 1080p high quality — `kim_compressandresizevideo.desktop:Av1hd1080High`

- **Menu path:** KIM6 — Video transcoding → AV1 1080p high quality
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 high quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 high quality; output size hd1080; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘AV1 1080p high quality’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### AV1 1080p balanced — `kim_compressandresizevideo.desktop:Av1hd1080Balanced`

- **Menu path:** KIM6 — Video transcoding → AV1 1080p balanced
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Use the AV1 balanced quality preset.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 balanced quality; output size hd1080; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘AV1 1080p balanced’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Custom AV1 settings… — `kim_compressandresizevideo.desktop:Av1Custom`

- **Menu path:** KIM6 — Video transcoding → Custom AV1 settings…
- **Dispatcher contract:** `kim_all video --size hd1080 --codec av1 --av1-quality custom --container mp4 -- %F`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** yes
- **Interactive choices:** Enter an AV1 CRF and speed preset when prompted; defaults are CRF 30 and speed 7.; Create or overwrite mode when asked.
- **Suggested choices:** Use this preset: AV1 custom quality (use CRF 30 and speed 7 for this check); output size hd1080; container mp4. Choose create mode if prompted.
- **Expected:** A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, qdbus, kdialog, selected optional encoder
- **Technical validation:** ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality.
- **Human inspection:** Check that the menu starts the operation named ‘Custom AV1 settings…’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Extract frame at timestamp… — `kim_compressandresizevideo.desktop:VideoFrameAt`

- **Menu path:** KIM6 — Video transcoding → Extract frame at timestamp…
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

### Extract automatic thumbnail — `kim_compressandresizevideo.desktop:VideoThumbnail`

- **Menu path:** KIM6 — Video transcoding → Extract automatic thumbnail
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

### Create video contact sheet… — `kim_compressandresizevideo.desktop:VideoContactSheet`

- **Menu path:** KIM6 — Video transcoding → Create video contact sheet…
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

### Extract audio… — `kim_compressandresizevideo.desktop:ExtractVideoAudio`

- **Menu path:** KIM6 — Video transcoding → Extract audio…
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

### Remove audio (copy video) — `kim_compressandresizevideo.desktop:MuteVideo`

- **Menu path:** KIM6 — Video transcoding → Remove audio (copy video)
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

### Create animated GIF from video… — `kim_compressandresizevideo.desktop:VideoToGif`

- **Menu path:** KIM6 — Video transcoding → Create animated GIF from video…
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

### KIM6 User Guide — `kim_compressandresizevideo.desktop:Manual`

- **Menu path:** KIM6 — Video transcoding → KIM6 User Guide
- **Dispatcher contract:** `kim_all manual`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** Installed docs/index.html and its stylesheet open.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Manual renders and stylesheet loads.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### License — `kim_compressandresizevideo.desktop:License`

- **Menu path:** KIM6 — Video transcoding → License
- **Dispatcher contract:** `kim_all license`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** Installed LICENSE.md opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Opened document is the installed GPL license.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### About KIM6 — `kim_compressandresizevideo.desktop:About`

- **Menu path:** KIM6 — Video transcoding → About KIM6
- **Dispatcher contract:** `kim_all about`
- **Select for the Dolphin context menu:** video-audio.mp4
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
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
| `kim_convertandrotate.desktop:ConvertWEBP` | `ConvertWEBP` | Convert to WebP | `kim_all convert --format webp -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertTIFF` | `ConvertTIFF` | Convert to TIFF | `kim_all convert --format tiff -- %F` | photo.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertPDF` | `ConvertPDF` | Convert to PDF | `kim_all convert --format pdf -- %F` | photo.tif | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertHEIC` | `ConvertHEIC` | Convert to HEIC/HEIF | `kim_all convert --format heic -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertAVIF` | `ConvertAVIF` | Convert to AVIF | `kim_all convert --format avif -- %F` | profile-wide.jpg | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertGIF` | `ConvertGIF` | Convert to GIF | `kim_all convert --format gif -- %F` | animated.gif | authorized_overwrite |
| `kim_convertandrotate.desktop:ConvertBMP` | `ConvertBMP` | Convert to BMP5 bitmap | `kim_all convert --format bmp --bmp5 -- %F` | photo.jpg | authorized_overwrite |
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

- **Menu path:** KIM6 — Convert and transform → Convert to JPEG
- **Dispatcher contract:** `kim_all convert --format jpg -- %F`
- **Select for the Dolphin context menu:** orientation-6.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to PNG — `kim_convertandrotate.desktop:ConvertPNG`

- **Menu path:** KIM6 — Convert and transform → Convert to PNG
- **Dispatcher contract:** `kim_all convert --format png -- %F`
- **Select for the Dolphin context menu:** transparent.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets PNG. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable PNG file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to PNG’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to WebP — `kim_convertandrotate.desktop:ConvertWEBP`

- **Menu path:** KIM6 — Convert and transform → Convert to WebP
- **Dispatcher contract:** `kim_all convert --format webp -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets WEBP. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable WEBP file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to WebP’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to TIFF — `kim_convertandrotate.desktop:ConvertTIFF`

- **Menu path:** KIM6 — Convert and transform → Convert to TIFF
- **Dispatcher contract:** `kim_all convert --format tiff -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets TIFF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable TIFF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to TIFF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to PDF — `kim_convertandrotate.desktop:ConvertPDF`

- **Menu path:** KIM6 — Convert and transform → Convert to PDF
- **Dispatcher contract:** `kim_all convert --format pdf -- %F`
- **Select for the Dolphin context menu:** photo.tif
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets PDF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable PDF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to PDF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to HEIC/HEIF — `kim_convertandrotate.desktop:ConvertHEIC`

- **Menu path:** KIM6 — Convert and transform → Convert to HEIC/HEIF
- **Dispatcher contract:** `kim_all convert --format heic -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets HEIC/HEIF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable HEIC/HEIF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to HEIC/HEIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to AVIF — `kim_convertandrotate.desktop:ConvertAVIF`

- **Menu path:** KIM6 — Convert and transform → Convert to AVIF
- **Dispatcher contract:** `kim_all convert --format avif -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets AVIF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable AVIF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to AVIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to GIF — `kim_convertandrotate.desktop:ConvertGIF`

- **Menu path:** KIM6 — Convert and transform → Convert to GIF
- **Dispatcher contract:** `kim_all convert --format gif -- %F`
- **Select for the Dolphin context menu:** animated.gif
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets GIF. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable GIF file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to GIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to BMP5 bitmap — `kim_convertandrotate.desktop:ConvertBMP`

- **Menu path:** KIM6 — Convert and transform → Convert to BMP5 bitmap
- **Dispatcher contract:** `kim_all convert --format bmp --bmp5 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets BMP. The BMP5 preset should produce a BMP5 bitmap. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable BMP file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to BMP5 bitmap’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to JPEG XL — `kim_convertandrotate.desktop:ConvertJXL`

- **Menu path:** KIM6 — Convert and transform → Convert to JPEG XL
- **Dispatcher contract:** `kim_all convert --format jxl -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG XL. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG XL file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG XL’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to JPEG 2000 (lossless) — `kim_convertandrotate.desktop:ConvertJP2Lossless`

- **Menu path:** KIM6 — Convert and transform → Convert to JPEG 2000 (lossless)
- **Dispatcher contract:** `kim_all convert --format jp2 --jp2-mode lossless -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG 2000. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG 2000 file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG 2000 (lossless)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to JPEG 2000 (lossy) — `kim_convertandrotate.desktop:ConvertJP2Lossy`

- **Menu path:** KIM6 — Convert and transform → Convert to JPEG 2000 (lossy)
- **Dispatcher contract:** `kim_all convert --format jp2 --jp2-mode lossy -- %F`
- **Select for the Dolphin context menu:** profile-wide.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets JPEG 2000. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable JPEG 2000 file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to JPEG 2000 (lossy)’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Convert to custom format… — `kim_convertandrotate.desktop:ConvertCustom`

- **Menu path:** KIM6 — Convert and transform → Convert to custom format…
- **Dispatcher contract:** `kim_all convert --custom-format -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom format for the custom entry; destination and create/overwrite prompts as provided by the action.
- **Suggested choices:** The menu preset targets THE FORMAT YOU CHOOSE. If a destination or filename dialog appears, save in this case folder and keep the matching extension.
- **Expected:** A readable THE FORMAT YOU CHOOSE file with a matching extension in this case folder.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Actual format matches selected format; decode succeeds; frame count is not silently lost.
- **Human inspection:** Check that the menu starts the operation named ‘Convert to custom format…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Auto-rotate using EXIF — `kim_convertandrotate.desktop:Rotateexif`

- **Menu path:** KIM6 — Convert and transform → Auto-rotate using EXIF
- **Dispatcher contract:** `kim_all rotate --exif -- %F`
- **Select for the Dolphin context menu:** orientation-6.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Choose automatic EXIF orientation correction. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Auto-rotate using EXIF’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate 90° — `kim_convertandrotate.desktop:Rotate90`

- **Menu path:** KIM6 — Convert and transform → Rotate 90°
- **Dispatcher contract:** `kim_all rotate --angle 90 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Use the 90 degree rotation. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate 90°’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate 180° — `kim_convertandrotate.desktop:Rotate180`

- **Menu path:** KIM6 — Convert and transform → Rotate 180°
- **Dispatcher contract:** `kim_all rotate --angle 180 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Use the 180 degree rotation. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate 180°’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate 270° — `kim_convertandrotate.desktop:Rotate270`

- **Menu path:** KIM6 — Convert and transform → Rotate 270°
- **Dispatcher contract:** `kim_all rotate --angle 270 -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** No additional menu-specific input; confirm the operation shown in the label.
- **Suggested choices:** Use the 270 degree rotation. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate 270°’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rotate custom angle… — `kim_convertandrotate.desktop:RotateCustom`

- **Menu path:** KIM6 — Convert and transform → Rotate custom angle…
- **Dispatcher contract:** `kim_all rotate --custom -- %F`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Custom angle for the custom entry; output policy follows the in-place action dialog.
- **Suggested choices:** Choose a custom angle such as 17 degrees. Confirm the direction by comparing the asymmetric fixture.
- **Expected:** The disposable image is changed in place and its visible orientation is corrected.
- **Source behavior:** `in_place`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, exiftool, qdbus, kdialog
- **Technical validation:** Decode, dimensions, frame count and source replacement are checked; visually confirm direction.
- **Human inspection:** Check that the menu starts the operation named ‘Rotate custom angle…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Flip vertically — `kim_convertandrotate.desktop:FlipVertical`

- **Menu path:** KIM6 — Convert and transform → Flip vertically
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

### Flip horizontally — `kim_convertandrotate.desktop:FlipHorizontal`

- **Menu path:** KIM6 — Convert and transform → Flip horizontally
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

## Publish and organize (`kim_publication.desktop.in`)

| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |
|---|---|---|---|---|---|
| `kim_publication.desktop:Gallery` | `Gallery` | Create an HTML gallery… | `kim_all gallery -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Collage` | `Collage` | Create a photo collage… | `kim_all collage -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
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
| `kim_publication.desktop:ContactSheet` | `ContactSheet` | Create a photo contact sheet… | `kim_all contactsheet -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Print` | `Print` | Create a print-layout PDF… | `kim_all print -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:TiffJoin` | `TiffJoin` | Join images into a multi-page TIFF… | `kim_all tiffjoin -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Animation` | `Animation` | Create an animated GIF… | `kim_all animate -- %F` | sequence-red.png, sequence-green.png, sequence-blue.png | derived |
| `kim_publication.desktop:Manual` | `Manual` | KIM6 User Guide | `kim_all manual` | photo.jpg | none |
| `kim_publication.desktop:License` | `License` | License | `kim_all license` | photo.jpg | none |
| `kim_publication.desktop:About` | `About` | About KIM6 | `kim_all about` | photo.jpg | none |

### Create an HTML gallery… — `kim_publication.desktop:Gallery`

- **Menu path:** KIM6 — Publish and organize → Create an HTML gallery…
- **Dispatcher contract:** `kim_all gallery -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Enter gallery title/author and layout/output options.
- **Suggested choices:** Enter title `KIM6 acceptance`, author `QA`, and 3 columns; choose this case folder for the gallery output if asked.
- **Expected:** A gallery directory with an index, full-size images and thumbnails.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, optional xdg-open
- **Technical validation:** index.html and all relative image/thumbnail references exist.
- **Human inspection:** Check that the menu starts the operation named ‘Create an HTML gallery…’. Open the gallery index in a browser, click a thumbnail and check the title, author and columns.

### Create a photo collage… — `kim_publication.desktop:Collage`

- **Menu path:** KIM6 — Publish and organize → Create a photo collage…
- **Dispatcher contract:** `kim_all collage -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose canvas/image size, layout, background, border, spacing/overlap and rotation/shadow options.
- **Suggested choices:** Use the defaults shown: 400x400 image size, 5x4 grid, 15% overlap and grey background; save in this case folder.
- **Expected:** A PNG collage containing all three colored source images.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Image decodes and selected tile ordering/layout is visible.
- **Human inspection:** Check that the menu starts the operation named ‘Create a photo collage…’. Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality.

### Rename images… — `kim_publication.desktop:Rename`

- **Menu path:** KIM6 — Publish and organize → Rename images…
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

### Rename by EXIF date… — `kim_publication.desktop:SortByDate`

- **Menu path:** KIM6 — Publish and organize → Rename by EXIF date…
- **Dispatcher contract:** `kim_all rename exifdate -- %F`
- **Select for the Dolphin context menu:** dated-photo.jpg, sequence-red.png, -leading ü [1].jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose naming mode, sequence/base or EXIF date format, destination, and conflict behavior as prompted.
- **Suggested choices:** Choose the EXIF date naming format shown by the dialog, then confirm the target names before proceeding.
- **Expected:** The selected files have new names in the chosen case folder; verify all files remain present and ordered.
- **Source behavior:** `rename`. Inputs are case-local disposable copies.
- **Dependencies:** qdbus, kdialog, optional exiftool for EXIF-date mode
- **Technical validation:** Each selected byte hash appears under the expected new name; no unrelated entry is lost.
- **Human inspection:** Check that the menu starts the operation named ‘Rename by EXIF date…’. Check the resulting names and verify every selected image remains present; compare the names with the selected mode.

### Strip metadata… — `kim_publication.desktop:StripMetadata`

- **Menu path:** KIM6 — Publish and organize → Strip metadata…
- **Dispatcher contract:** `kim_all stripmeta -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Suggested choices:** Confirm the requested all metadata removal when prompted. Choose create mode for this check if offered.
- **Expected:** A result with all metadata removed; image pixels and unrelated metadata should follow the action's documented policy.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Check that the menu starts the operation named ‘Strip metadata…’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

### Remove GPS coordinates… — `kim_publication.desktop:StripGPS`

- **Menu path:** KIM6 — Publish and organize → Remove GPS coordinates…
- **Dispatcher contract:** `kim_all stripmeta --mode gps -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Suggested choices:** Confirm the requested GPS/location fields only removal when prompted. Choose create mode for this check if offered.
- **Expected:** A result with GPS/location fields only removed; image pixels and unrelated metadata should follow the action's documented policy.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Check that the menu starts the operation named ‘Remove GPS coordinates…’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

### Remove recognized AI metadata… — `kim_publication.desktop:RemoveAIMetadata`

- **Menu path:** KIM6 — Publish and organize → Remove recognized AI metadata…
- **Dispatcher contract:** `kim_all stripmeta --mode ai -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Metadata scope, and create/overwrite policy when supported by the selected mode.
- **Suggested choices:** Confirm the requested recognized AI-generation metadata only removal when prompted. Choose create mode for this check if offered.
- **Expected:** A result with recognized AI-generation metadata only removed; image pixels and unrelated metadata should follow the action's documented policy.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Decode, pixel/frame integrity and requested tag scope are checked.
- **Human inspection:** Check that the menu starts the operation named ‘Remove recognized AI metadata…’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

### Set creator and copyright… — `kim_publication.desktop:SetCopyright`

- **Menu path:** KIM6 — Publish and organize → Set creator and copyright…
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

### Adjust camera timestamps… — `kim_publication.desktop:AdjustCaptureTime`

- **Menu path:** KIM6 — Publish and organize → Adjust camera timestamps…
- **Dispatcher contract:** `kim_all timeshift --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose offset direction and the camera timestamp fields to shift.
- **Suggested choices:** Choose a one-hour forward shift and the default capture-date fields; review the before/after confirmation before accepting.
- **Expected:** The selected EXIF camera dates move forward by one hour; filesystem modification time is unchanged.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, identify, qdbus, kdialog
- **Technical validation:** Selected camera date tags read back with expected offset; filesystem mtime unchanged.
- **Human inspection:** Check that the menu starts the operation named ‘Adjust camera timestamps…’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

### Synchronize photo/file dates… — `kim_publication.desktop:DateSync`

- **Menu path:** KIM6 — Publish and organize → Synchronize photo/file dates…
- **Dispatcher contract:** `kim_all datesync --interactive -- %F`
- **Select for the Dolphin context menu:** metadata.jpg
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose EXIF-to-filesystem or filesystem-to-EXIF; file-to-EXIF also asks which date tags to update.
- **Suggested choices:** Choose choose EXIF to file for this first run. Review the displayed before/after time and confirm the direction explicitly.
- **Expected:** The selected date values match in the chosen direction; image bytes remain unchanged for EXIF-to-file mode.
- **Source behavior:** `authorized_overwrite`. Inputs are case-local disposable copies.
- **Dependencies:** exiftool, magick, qdbus, kdialog
- **Technical validation:** Compare EXIF date and filesystem mtime in the selected direction.
- **Human inspection:** Check that the menu starts the operation named ‘Synchronize photo/file dates…’. Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case.

### Create MP4 slideshow… — `kim_publication.desktop:Slideshow`

- **Menu path:** KIM6 — Publish and organize → Create MP4 slideshow…
- **Dispatcher contract:** `kim_all slideshow --interactive -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose slide duration, frame size/rate, background and ordering options.
- **Suggested choices:** Use 3 seconds per photo, 1280x720, 25 fps, black background and the natural filename ordering; save as `slideshow.mp4` in this case folder.
- **Expected:** A silent H.264 MP4 showing red, green, then blue slides, each for about 3 seconds.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** ffmpeg, ffprobe, magick, identify, libx264, qdbus, kdialog
- **Technical validation:** Automated: ffprobe confirms H.264 MP4, observed dimensions, selected frame rate, approximate duration, frame count when reported, no audio, and full decode. Human: compare image order and dimensions to the interactive choices.
- **Human inspection:** Check that the menu starts the operation named ‘Create MP4 slideshow…’. Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality.

### Create a PDF album… — `kim_publication.desktop:Album`

- **Menu path:** KIM6 — Publish and organize → Create a PDF album…
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

### Create a photo contact sheet… — `kim_publication.desktop:ContactSheet`

- **Menu path:** KIM6 — Publish and organize → Create a photo contact sheet…
- **Dispatcher contract:** `kim_all contactsheet -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose page size/orientation, grid, labels, image fit, background, resolution and title.
- **Suggested choices:** Follow the choices printed by the action and save any result in this case folder.
- **Expected:** A printable PDF contact sheet with the selected grid, labels and page size.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog, PDF delegate
- **Technical validation:** Automated: pdfinfo reports readable pages and correct physical size. Human: inspect image order, number/filename labels, grid and pagination.
- **Human inspection:** Check that the menu starts the operation named ‘Create a photo contact sheet…’. Check that the result matches the expected behavior below.

### Create a print-layout PDF… — `kim_publication.desktop:Print`

- **Menu path:** KIM6 — Publish and organize → Create a print-layout PDF…
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

### Join images into a multi-page TIFF… — `kim_publication.desktop:TiffJoin`

- **Menu path:** KIM6 — Publish and organize → Join images into a multi-page TIFF…
- **Dispatcher contract:** `kim_all tiffjoin -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose the output location/name; selected order is used.
- **Suggested choices:** Accept the suggested TIFF output name and choose this case folder if a destination is requested.
- **Expected:** A multi-page TIFF whose pages follow the selected red, green, blue order.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Automated: TIFF fully decodes and page count matches selected input frame count. Human: inspect page order.
- **Human inspection:** Check that the menu starts the operation named ‘Join images into a multi-page TIFF…’. Open the TIFF as pages and check that red, green, then blue appear in that order.

### Create an animated GIF… — `kim_publication.desktop:Animation`

- **Menu path:** KIM6 — Publish and organize → Create an animated GIF…
- **Dispatcher contract:** `kim_all animate -- %F`
- **Select for the Dolphin context menu:** sequence-red.png, sequence-green.png, sequence-blue.png
- **Files passed to dispatcher:** yes
- **Interactive choices:** Choose frame delay and animation settings.
- **Suggested choices:** Use a 100-centisecond frame delay and loop count 0 (infinite); save the GIF in this case folder.
- **Expected:** An animated GIF showing red, green, then blue frames and looping continuously.
- **Source behavior:** `derived`. Inputs are case-local disposable copies.
- **Dependencies:** magick, identify, qdbus, kdialog
- **Technical validation:** Automated: GIF fully decodes and frame count matches selected input frame count. Human: inspect frame order, delay and loop behavior.
- **Human inspection:** Check that the menu starts the operation named ‘Create an animated GIF…’. Open the GIF in an animation-capable viewer and check red, green, blue order, delay and looping.

### KIM6 User Guide — `kim_publication.desktop:Manual`

- **Menu path:** KIM6 — Publish and organize → KIM6 User Guide
- **Dispatcher contract:** `kim_all manual`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** Installed docs/index.html and its stylesheet open.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Manual renders and stylesheet loads.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### License — `kim_publication.desktop:License`

- **Menu path:** KIM6 — Publish and organize → License
- **Dispatcher contract:** `kim_all license`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** Installed LICENSE.md opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** xdg-open
- **Technical validation:** Opened document is the installed GPL license.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

### About KIM6 — `kim_publication.desktop:About`

- **Menu path:** KIM6 — Publish and organize → About KIM6
- **Dispatcher contract:** `kim_all about`
- **Select for the Dolphin context menu:** photo.jpg
- **Files passed to dispatcher:** no (context file only)
- **Interactive choices:** No processing dialog; open the informational resource and close it.
- **Suggested choices:** Open the item and close it after checking the installed information resource.
- **Expected:** KDialog About text opens.
- **Source behavior:** `none`. Inputs are case-local disposable copies.
- **Dependencies:** kdialog
- **Technical validation:** Dialog is legible and identifies KIM6.
- **Human inspection:** Confirm the expected informational resource opens, is readable, and can be closed.

## Status meanings

The CLI result log separates **GUI verified**, **CLI verified**, **GUI blocked by KDE**, and **Not tested**. Only a person invoking a menu in Dolphin can record GUI verification. `validate` performs technical checks only.
